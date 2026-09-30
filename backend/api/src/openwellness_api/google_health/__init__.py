"""Google Health in ``ow_api`` (opserver Phase 10.1, GHA-01, GHA-02).

Four routes, all under the edge group ``/api/googleHealth`` (D-05):

- ``POST /api/googleHealth/links``: staff mint a participant-bound link.
  Router-level ``require_write_principal`` plus the ``admin`` role.
- ``GET /api/googleHealth/authorize`` and ``GET /api/googleHealth/finishAuth``:
  the participant's browser, unauthenticated by design. Each carries the
  ``x-allow-unauthenticated`` marker; the link and state tokens are their
  credentials (D-11).
- ``POST /api/googleHealth/notifications``: Google's webhook subscriber,
  unauthenticated by marker; it checks the shared ``Authorization`` secret
  and the ``GOOGLE-HEALTH-API-SIGNATURE`` itself and only enqueues
  (:mod:`.notifications`).

The routes read ``app.state.google_health_deps``, built in the lifespan by
:func:`build_google_health_deps`. While a required setting is unset or
invalid every route answers 503 with a generic page.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from ..config import AuthSettings
from ..deps.principal import ALLOW_UNAUTHENTICATED, require_write_principal
from ..event_handlers.celery_producer import CeleryTaskPublisher, ProducerSettings
from ..event_handlers.mongo_readers import MongoParticipantReader
from ..event_handlers.ports import TaskPublisher
from .google_client import GoogleOAuthClient, RequestsGoogleOAuthClient
from .notifications import build_notifications_router
from .oauth import (
    GoogleHealthDeps,
    authorize,
    create_link,
    finish_auth,
    get_google_health_deps,
)
from .settings import GoogleHealthSettings
from .signature import SignatureVerifier, TinkSignatureVerifier
from .store import GoogleHealthStore
from .tokens import GoogleHealthTokens

logger = logging.getLogger(__name__)

LINKS_PATH = "/api/googleHealth/links"
AUTHORIZE_PATH = "/api/googleHealth/authorize"
FINISH_AUTH_PATH = "/api/googleHealth/finishAuth"

__all__ = [
    "GoogleHealthDeps",
    "build_google_health_deps",
    "build_google_health_router",
    "get_google_health_deps",
]


def build_google_health_router() -> APIRouter:
    staff = APIRouter(dependencies=[Depends(require_write_principal)])
    staff.add_api_route(LINKS_PATH, create_link, methods=["POST"], include_in_schema=False)

    browser = APIRouter()
    browser.add_api_route(
        AUTHORIZE_PATH,
        authorize,
        methods=["GET"],
        include_in_schema=False,
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
    )
    browser.add_api_route(
        FINISH_AUTH_PATH,
        finish_auth,
        methods=["GET"],
        include_in_schema=False,
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
    )

    router = APIRouter()
    router.include_router(staff)
    router.include_router(browser)
    router.include_router(build_notifications_router())
    return router


def build_google_health_deps(
    *,
    db: Any,
    redis: Any,
    producer_settings: ProducerSettings,
    settings: GoogleHealthSettings | None = None,
    google: GoogleOAuthClient | None = None,
    publisher: TaskPublisher | None = None,
    auth_signing_secret: str | None = None,
    signature_verifier: SignatureVerifier | None = None,
) -> GoogleHealthDeps:
    """Production deps over the shared Mongo handle and Redis client.

    Validates the settings once: unset keys (by name) and, when any Google
    key is set, the violated rules of :meth:`GoogleHealthSettings.problems`.
    Any finding logs one WARNING listing names only, never a value, and makes
    every Google Health route answer 503.

    ``auth_signing_secret`` defaults to ``API_AUTH_JWT_SECRET`` read through
    :class:`AuthSettings`; it is only compared, never logged or used to sign.

    ``signature_verifier`` defaults to a :class:`TinkSignatureVerifier` on
    ``settings.keyset_url``; it fetches the keyset on first use, in the
    threadpool, never here.
    """
    gh_settings = settings if settings is not None else GoogleHealthSettings()
    if auth_signing_secret is None:
        auth_signing_secret = AuthSettings().jwt_secret
    missing = gh_settings.missing_keys()
    any_set = len(missing) < len(gh_settings.required_keys())
    rules = gh_settings.problems(auth_signing_secret) if any_set else []
    if missing or rules:
        parts = []
        if missing:
            parts.append("unset " + ", ".join(missing))
        if rules:
            parts.append("invalid " + ", ".join(rules))
        logger.warning("googleHealth routes disabled until fixed: %s", "; ".join(parts))
    return GoogleHealthDeps(
        settings=gh_settings,
        tokens=GoogleHealthTokens(gh_settings, redis),
        store=GoogleHealthStore(db),
        participants=MongoParticipantReader(db),
        google=google if google is not None else RequestsGoogleOAuthClient(gh_settings),
        publisher=publisher if publisher is not None else CeleryTaskPublisher(producer_settings),
        disabled=(*missing, *rules),
        signature_verifier=(
            signature_verifier
            if signature_verifier is not None
            else TinkSignatureVerifier(gh_settings.keyset_url)
        ),
    )
