"""Principal (caller identity) dependency — JWT-aware, backwards-compatible.

``get_principal`` is the legacy dependency ~37 resource routes use only to
stamp ``updated_by``. It is now JWT-aware (a valid ``Authorization: Bearer``
access token yields an AUTHENTICATED principal with roles/participant), but it
preserves a HARD never-raise contract: a missing/malformed/expired bearer must
NOT 401 here — it degrades to the legacy ``X-Principal-Id`` (or ``anonymous``)
stamp so existing routes keep working unchanged.

``require_principal`` is the strict, enforcement-gated dependency new sensitive
routes opt into. It is the ONLY place a 401 may originate, and only when
``AuthSettings.enforce_principal`` is True (permissive rollout otherwise: it
logs a would-be-401 and lets the anonymous principal through).

CIRCULAR-IMPORT NOTE: do NOT import ``auth.errors`` or ``auth.service`` at
module level — that would create a cycle via ``common.handlers``. The 401
envelope is built with the leaf-module ``errors.responses.build_error``, and
the token-service exception type is referenced only via a broad
``except Exception`` (no import of it needed) so verification failures degrade
to anonymous regardless of the concrete error type.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from ..errors.responses import build_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Principal:
    """The caller of an API request.

    ``id`` is the legacy contract every existing route depends on (it stamps
    ``updated_by``). The remaining fields are ADDITIVE and all defaulted, so
    every existing ``Principal(id=...)`` construction keeps working.
    """

    id: str
    """A free-form identifier. ``"anonymous"`` if no header/token was supplied."""

    roles: tuple[str, ...] = ()
    """Roles from a verified access token; empty for unauthenticated callers."""

    participant: str | None = None
    """The bare participant id from the JWT ``participant`` claim, if any."""

    is_authenticated: bool = False
    """True only when a valid bearer access token was verified."""


def get_principal(
    request: Request,
    x_principal_id: Annotated[str | None, Header(alias="X-Principal-Id")] = None,
) -> Principal:
    """Resolve the caller identity. NEVER raises.

    FastAPI injects ``request`` automatically, so existing
    ``Depends(get_principal)`` call sites need no change.

    A valid ``Authorization: Bearer <jwt>`` access token yields an
    AUTHENTICATED principal. ANY failure in bearer handling (no
    ``auth_container`` wired, invalid/expired token, or anything unexpected)
    degrades to the anonymous/legacy path. This is a HARD contract: a
    malformed bearer must NOT 401 here — enforcing auth is
    :func:`require_principal`'s job, not this one's.
    """
    auth_header = request.headers.get("authorization") or ""
    if auth_header[:7].lower() == "bearer ":
        token = auth_header[7:].strip()
        if token:
            try:
                token_service = request.app.state.auth_container.token_service()
                claims = token_service.verify_access(token)
                return Principal(
                    id=claims.sub,
                    roles=tuple(claims.roles),  # already a tuple; copy is cheap/defensive
                    participant=claims.participant,  # bare pid (the JWT 'participant' claim)
                    is_authenticated=True,
                )
            except Exception:
                # Never-raise contract: degrade to anonymous on ANY failure
                # (missing container, InvalidAccessToken, unexpected error).
                # Keyed by nothing sensitive — no token, no email.
                logger.debug("bearer verification failed; falling back to anonymous")

    # Anonymous fallback preserves legacy behavior: an invalid bearer falls
    # back to the X-Principal-Id stamp (NOT a 401).
    return Principal(id=x_principal_id or "anonymous", is_authenticated=False)


def require_principal(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    """Strict, enforcement-gated principal. The ONLY source of a 401.

    Reads ``AuthSettings.enforce_principal`` off the live auth container (a
    missing container is treated as ``enforce=False`` so this never explodes
    when the container isn't wired). New sensitive routes opt into this; it is
    NOT applied to any existing route in this task.
    """
    if principal.is_authenticated:
        return principal

    enforce = False
    auth_container = getattr(request.app.state, "auth_container", None)
    if auth_container is not None:
        try:
            enforce = bool(auth_container.auth_settings().enforce_principal)
        except Exception:
            # Defensive: a half-wired container must not turn a permissive
            # rollout into a hard failure. Treat as enforce=False.
            enforce = False

    if enforce:
        raise HTTPException(
            status_code=401,
            detail=build_error(401, "UNAUTHENTICATED", "Authentication required."),
        )

    # Permissive rollout: observe would-be-401 traffic before flipping
    # enforcement per-environment. WARNING is deliberate — during the rollout
    # window these are a signal we want visible (not filtered out at INFO) so
    # traffic can be assessed before a route's enforcement is turned on.
    logger.warning(
        "would-be 401: unauthenticated request to %s (enforce off)",
        request.url.path,
    )
    return principal
