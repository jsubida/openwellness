"""Link and state tokens, their Redis single-use markers, and the migration locks.

Contract: opserver ``docs/google-health.md``, "Link token, OAuth state and
browser binding" and invariant I3.

- The **link** (``t``) is an HS256 JWT signed with the link secret,
  ``aud="googleHealth:link"``, ``sub=<participantId>``, 72 h.
- The OAuth **state** is an HS256 JWT signed with the state secret,
  ``aud="googleHealth:state"``, 15 min, bound to the initiating browser by
  ``bh`` (SHA-256 of the ``gh_oauth`` cookie) and made single-use by the
  Redis nonce ``gh:state:<jti>``. It also carries the link's ``jti`` and
  ``exp`` (``lnk``, ``lx``), so finishAuth can claim the link.
- The **link claim** ``gh:link:claim:<jti>`` is taken before the code
  exchange and kept after the insert: it is the only consumed-link marker.

``ow_api`` runs two uvicorn workers, so nothing lives in process memory.
Neither secret is the API's access-token secret; the ``aud`` values stop one
token being accepted as the other. Every failure raises a
:class:`GoogleHealthTokenError` subclass whose message is fixed: never a
token, a claim or the underlying library's message.
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import jwt

from .settings import GoogleHealthSettings

ISSUER: Final = "openwellness-api"
LINK_AUDIENCE: Final = "googleHealth:link"
STATE_AUDIENCE: Final = "googleHealth:state"
_ALGORITHM: Final = "HS256"

STATE_KEY: Final = "gh:state:{jti}"
LINK_CLAIM_KEY: Final = "gh:link:claim:{jti}"


class GoogleHealthTokenError(Exception):
    """A link or state was refused, or its Redis marker could not be used."""

    message = "token rejected"

    def __init__(self) -> None:
        super().__init__(self.message)


class TokenInvalid(GoogleHealthTokenError):
    message = "token invalid"


class StateBrowserMismatch(GoogleHealthTokenError):
    message = "state not bound to this browser"


class StateReplayed(GoogleHealthTokenError):
    message = "state already used"


class TokenStoreError(GoogleHealthTokenError):
    message = "token store unavailable"


@dataclass(frozen=True)
class LinkClaims:
    participant_id: str
    jti: str
    exp: int


@dataclass(frozen=True)
class StateClaims:
    participant_id: str
    jti: str
    link_jti: str
    link_exp: int


class GoogleHealthTokens:
    """Mints and verifies the two tokens against one Redis."""

    def __init__(
        self,
        settings: GoogleHealthSettings,
        redis: Any,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._clock = clock

    def _now(self) -> int:
        return int(self._clock())

    # --- link -------------------------------------------------------------

    def mint_link(self, participant_id: str) -> tuple[str, int]:
        now = self._now()
        exp = now + self._settings.link_ttl_seconds
        claims = {
            "iss": ISSUER,
            "aud": LINK_AUDIENCE,
            "sub": participant_id,
            "iat": now,
            "exp": exp,
            "jti": secrets.token_urlsafe(16),
        }
        return jwt.encode(claims, self._settings.link_secret, algorithm=_ALGORITHM), exp

    def verify_link(self, token: str | None) -> LinkClaims:
        claims = self._decode(token, self._settings.link_secret, LINK_AUDIENCE)
        return LinkClaims(
            participant_id=_str_claim(claims, "sub"),
            jti=_str_claim(claims, "jti"),
            exp=_int_claim(claims, "exp"),
        )

    # --- state ------------------------------------------------------------

    def mint_state(
        self, participant_id: str, link_jti: str, link_exp: int, browser_hash: str
    ) -> str:
        now = self._now()
        jti = secrets.token_urlsafe(16)
        ttl = self._settings.state_ttl_seconds
        claims = {
            "iss": ISSUER,
            "aud": STATE_AUDIENCE,
            "sub": participant_id,
            "iat": now,
            "exp": now + ttl,
            "jti": jti,
            "lnk": link_jti,
            "lx": link_exp,
            "bh": browser_hash,
        }
        try:
            stored = self._redis.set(STATE_KEY.format(jti=jti), "1", nx=True, ex=ttl)
        except Exception as exc:
            raise TokenStoreError() from exc
        if not stored:
            raise TokenStoreError()
        return jwt.encode(claims, self._settings.state_secret, algorithm=_ALGORITHM)

    def consume_state(self, token: str | None, browser_hash: str) -> StateClaims:
        """Verify ``token`` and its browser binding, then consume the nonce.

        The binding is checked before the nonce is touched, so a request from
        another browser cannot burn the legitimate browser's state.
        """
        claims = self._decode(token, self._settings.state_secret, STATE_AUDIENCE)
        bound = claims.get("bh")
        if not isinstance(bound, str) or not hmac.compare_digest(
            bound.encode("ascii", "replace"), browser_hash.encode("ascii", "replace")
        ):
            raise StateBrowserMismatch()
        state = StateClaims(
            participant_id=_str_claim(claims, "sub"),
            jti=_str_claim(claims, "jti"),
            link_jti=_str_claim(claims, "lnk"),
            link_exp=_int_claim(claims, "lx"),
        )
        try:
            deleted = self._redis.delete(STATE_KEY.format(jti=state.jti))
        except Exception as exc:
            raise TokenStoreError() from exc
        if deleted != 1:
            raise StateReplayed()
        return state

    # --- link claim (I3) --------------------------------------------------

    def claim_link(self, jti: str, exp: int) -> bool:
        """Take the link for this completion. ``False`` when already claimed."""
        ttl = max(1, exp - self._now())
        try:
            return bool(self._redis.set(LINK_CLAIM_KEY.format(jti=jti), "1", nx=True, ex=ttl))
        except Exception as exc:
            raise TokenStoreError() from exc

    def release_link(self, jti: str) -> None:
        """Give the link back after a failure before the insert. Best effort."""
        try:
            self._redis.delete(LINK_CLAIM_KEY.format(jti=jti))
        except Exception:
            pass

    def is_link_claimed(self, jti: str) -> bool:
        try:
            return bool(self._redis.exists(LINK_CLAIM_KEY.format(jti=jti)))
        except Exception as exc:
            raise TokenStoreError() from exc

    # --- helpers ----------------------------------------------------------

    def _decode(self, token: str | None, secret: str, audience: str) -> dict[str, Any]:
        if not token or not isinstance(token, str):
            raise TokenInvalid()
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=[_ALGORITHM],
                audience=audience,
                issuer=ISSUER,
                options={"require": ["exp", "iat", "jti", "sub", "aud", "iss"]},
            )
        except Exception as exc:
            raise TokenInvalid() from exc


def _str_claim(claims: dict[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise TokenInvalid()
    return value


def _int_claim(claims: dict[str, Any], name: str) -> int:
    value = claims.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TokenInvalid()
    return value
