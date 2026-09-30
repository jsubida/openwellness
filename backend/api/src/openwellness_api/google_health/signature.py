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

Nothing here logs the signature, the body or key material.
"""

from __future__ import annotations

from typing import Protocol


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
