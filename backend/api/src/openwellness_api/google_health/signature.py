"""Verification of ``GOOGLE-HEALTH-API-SIGNATURE`` (opserver Phase 10.1, GHA-02).

Google signs the raw JSON body of every notification with Tink's
``PublicKeySign`` (ECDSA P-256, SHA-256) and sends the Base64 signature in the
``GOOGLE-HEALTH-API-SIGNATURE`` header. The public keyset rotates every 30
days and is published at a permanent gstatic URL
(https://developers.google.com/health/webhooks, "Signature verification").

The receiver depends only on the :class:`SignatureVerifier` port. The two
outcomes it must tell apart are:

- the signature is invalid (``verify`` returns ``False``): the route answers
  401 and Google does not redeliver;
- the key needed to judge it is not available (``verify`` raises
  :class:`SignatureVerificationUnavailable`): the route answers 503 so Google
  retries, because a genuine notification signed under a newly rotated key
  must not be discarded.

Nothing here logs the signature, the body, a key id or key material.

:class:`TinkSignatureVerifier` implements the port with Tink's
``PublicKeyVerify`` over the published JSON public keyset (API names checked
against tink 1.16.1: ``tink.signature.register``,
``tink.json_proto_keyset_format.parse_without_secret``,
``KeysetHandle.primitive(signature.PublicKeyVerify)``, ``verify`` raising
``tink.TinkError``). Rotation (T-10.1-81, T-10.1-27):

- the Tink prefix (``0x01`` then a 4-byte big-endian key id) names the key;
  a key id in the cached keyset that does not verify is ``False`` and never
  refetches;
- an unknown key id refetches the keyset, at most once per
  :data:`REFETCH_FLOOR_SECONDS` (a failed attempt counts); if a fetch made
  during the call still lacks the key the answer is ``False``;
- an unknown key id when the floor forbids a refetch, a failed or
  unparseable fetch, or no keyset at all raises
  :class:`SignatureVerificationUnavailable`, so Google redelivers.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final, Protocol

import requests
import tink
from tink import json_proto_keyset_format, signature
from tink.proto import common_pb2, ecdsa_pb2

logger = logging.getLogger(__name__)

DEFAULT_KEYSET_URL: Final = (
    "https://www.gstatic.com/googlehealthapi/webhooks/webhooks_public_keyset.json"
)
"""Google's permanent public keyset URL (webhooks page, "Signature verification")."""

REFETCH_FLOOR_SECONDS: Final = 60.0
FETCH_TIMEOUT_SECONDS: Final = 5

_LOG: Final = "googleHealth/signature"
_TINK_PREFIX: Final = 0x01
_PREFIX_LENGTH: Final = 5
_ECDSA_TYPE_URL: Final = "type.googleapis.com/google.crypto.tink.EcdsaPublicKey"

signature.register()

# Generated protobuf modules ship without type stubs; bind the three names once.
_EcdsaPublicKey: Any = getattr(ecdsa_pb2, "EcdsaPublicKey")
_EllipticCurveType: Any = getattr(common_pb2, "EllipticCurveType")
_HashType: Any = getattr(common_pb2, "HashType")


class SignatureVerificationUnavailable(Exception):
    """The verifier cannot judge the signature right now (no usable key).

    The message never carries the signature, the body or key material.
    """


class SignatureVerifier(Protocol):
    """Checks ``GOOGLE-HEALTH-API-SIGNATURE`` over the exact raw body bytes."""

    def verify(self, signature_b64: str, raw_body: bytes) -> bool:
        """``True`` only for a valid signature by a key in Google's keyset.

        ``False`` for a malformed, tampered or wrong-key signature. Raises
        :class:`SignatureVerificationUnavailable` when no usable key is
        available (a failed or rate-floored keyset refetch). Blocking: the
        route calls it in the threadpool.
        """
        ...


class KeysetError(Exception):
    """The keyset could not be fetched or parsed. The message is a fixed reason code."""


@dataclass(frozen=True)
class PublicKeyInfo:
    """One ENABLED key of a parsed keyset (no key material)."""

    key_id: int
    curve: str
    hash: str


@dataclass(frozen=True)
class ParsedKeyset:
    """A keyset ready to verify with: the Tink primitive and its key ids."""

    keys: tuple[PublicKeyInfo, ...]
    primitive: Any

    @property
    def key_ids(self) -> frozenset[int]:
        return frozenset(key.key_id for key in self.keys)


def parse_keyset(text: str) -> ParsedKeyset:
    """Parse a Tink JSON public keyset into a ``PublicKeyVerify`` primitive.

    Raises :class:`KeysetError` (fixed reason code) when the text is not a
    public keyset Tink accepts or holds no ENABLED ECDSA key.
    """
    try:
        document = json.loads(text)
        entries = document["key"]
        keys = tuple(
            _key_info(entry) for entry in entries if entry.get("status") == "ENABLED"
        )
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise KeysetError("keyset_malformed") from exc
    if not keys:
        raise KeysetError("keyset_empty")
    try:
        handle = json_proto_keyset_format.parse_without_secret(text)
        primitive = handle.primitive(signature.PublicKeyVerify)
    except tink.TinkError as exc:
        raise KeysetError("keyset_rejected") from exc
    return ParsedKeyset(keys=keys, primitive=primitive)


def _key_info(entry: dict[str, Any]) -> PublicKeyInfo:
    data = entry["keyData"]
    if data["typeUrl"] != _ECDSA_TYPE_URL or entry["outputPrefixType"] != "TINK":
        raise ValueError("unsupported key")
    try:
        key = _EcdsaPublicKey.FromString(base64.b64decode(data["value"], validate=True))
    except Exception as exc:  # protobuf DecodeError, binascii.Error
        raise ValueError("undecodable key") from exc
    return PublicKeyInfo(
        key_id=int(entry["keyId"]),
        curve=_EllipticCurveType.Name(key.params.curve),
        hash=_HashType.Name(key.params.hash_type),
    )


def _decode_signature(signature_b64: str) -> tuple[int, bytes] | None:
    """``(key_id, raw_signature)`` for a TINK-prefixed Base64 signature, else ``None``."""
    try:
        raw = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) <= _PREFIX_LENGTH or raw[0] != _TINK_PREFIX:
        return None
    return int.from_bytes(raw[1:_PREFIX_LENGTH], "big"), raw


class TinkSignatureVerifier:
    """:class:`SignatureVerifier` over Google's published keyset, cached in process.

    ``fetch`` returns the keyset JSON text (default: GET ``keyset_url`` with a
    5 s timeout); ``clock`` is monotonic seconds. Construction fetches nothing:
    the first ``verify`` does. Safe across threadpool threads: one lock guards
    the cache and serializes fetches, so concurrent unknown key ids cause one
    refetch. Blocking; the route calls it in the threadpool.
    """

    def __init__(
        self,
        keyset_url: str = DEFAULT_KEYSET_URL,
        fetch: Callable[[], str] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.keyset_url = keyset_url
        self._fetch = fetch if fetch is not None else self._http_fetch
        self._clock = clock if clock is not None else time.monotonic
        self._lock = threading.Lock()
        self._keyset: ParsedKeyset | None = None
        self._last_attempt: float | None = None

    def verify(self, signature_b64: str, raw_body: bytes) -> bool:
        decoded = _decode_signature(signature_b64)
        if decoded is None:
            return False
        key_id, raw_signature = decoded
        keyset = self._keyset_for(key_id)
        if keyset is None:
            return False
        try:
            keyset.primitive.verify(raw_signature, raw_body)
        except tink.TinkError:
            return False
        return True

    def _keyset_for(self, key_id: int) -> ParsedKeyset | None:
        """The keyset to judge ``key_id`` with, ``None`` when it is definitively absent.

        Raises :class:`SignatureVerificationUnavailable` when no keyset able to
        judge it can be had right now.
        """
        with self._lock:
            cached = self._keyset
            if cached is not None and key_id in cached.key_ids:
                return cached
            now = self._clock()
            if self._last_attempt is not None and now - self._last_attempt < REFETCH_FLOOR_SECONDS:
                logger.warning("%s unavailable: refetch_floored", _LOG)
                raise SignatureVerificationUnavailable("refetch_floored")
            self._last_attempt = now
            reason = "unknown_key_id" if cached is not None else "no_keyset"
            try:
                fresh = parse_keyset(self._fetch())
            except Exception as exc:
                logger.warning(
                    "%s keyset fetch failed (%s): %s", _LOG, reason, _reason_code(exc)
                )
                raise SignatureVerificationUnavailable("keyset_unavailable") from None
            self._keyset = fresh
            logger.info("%s keyset fetched (%s): %d keys", _LOG, reason, len(fresh.keys))
            return fresh if key_id in fresh.key_ids else None

    def _http_fetch(self) -> str:
        response = requests.get(self.keyset_url, timeout=FETCH_TIMEOUT_SECONDS)
        if response.status_code != 200:
            raise KeysetError(f"http_{response.status_code}")
        return response.text


def _reason_code(exc: Exception) -> str:
    """A fixed-shape reason: our own reason codes, else the exception class name."""
    if isinstance(exc, KeysetError) and exc.args and isinstance(exc.args[0], str):
        return exc.args[0]
    return type(exc).__name__
