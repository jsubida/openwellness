"""Uniform, anti-enumeration HTTP error helpers for the auth surface.

These mirror the ``common/handlers.py:bad_request`` pattern: each helper
returns a FastAPI :class:`~fastapi.HTTPException` carrying the AIP-193 error
envelope inside ``detail``. The registered ``HTTPException`` handler
(``errors/handlers.py``) unwraps that envelope, so the wire body never gains an
extra ``{"detail": ...}`` wrap.

Anti-enumeration is the whole point here:

- ``UNIFORM_SEND_MESSAGE`` is the SAME 200 body for every send, eligible or
  not, so a caller can never learn whether an account/participant exists.
- ``invalid_code()`` is the SAME 400 for every verify failure (missing,
  expired, wrong, unknown email) — the reason is never revealed.
- ``unauthenticated()`` is the 401 used for refresh/revoke auth failures.

The service NEVER builds an error message that depends on a not-found /
already-registered / wrong-state condition; it only ever raises these helpers.
"""

from __future__ import annotations

from fastapi import HTTPException

from openwellness_api.errors.responses import build_error


#: Generic 200 send message that does NOT reveal account existence.
UNIFORM_SEND_MESSAGE = (
    "If your account is eligible, a verification code has been sent to "
    "your email."
)

#: Fixed generic message for ALL verify failures (anti-enumeration: identical
#: 400 regardless of the underlying reason).
_INVALID_CODE_MESSAGE = "The code is invalid or has expired."


def invalid_code() -> HTTPException:
    """A 400 ``INVALID_ARGUMENT`` used for EVERY verify failure.

    The message is fixed and reason-free: a wrong code, an expired/missing
    record, and an unknown email all surface as this identical response so a
    verify can never be used to probe account state.
    """
    return HTTPException(
        status_code=400,
        detail=build_error(400, "INVALID_ARGUMENT", _INVALID_CODE_MESSAGE),
    )


def unauthenticated(message: str = "Authentication required.") -> HTTPException:
    """A 401 ``UNAUTHENTICATED`` for refresh/revoke auth failures."""
    return HTTPException(
        status_code=401,
        detail=build_error(401, "UNAUTHENTICATED", message),
    )


__all__ = [
    "UNIFORM_SEND_MESSAGE",
    "invalid_code",
    "unauthenticated",
]
