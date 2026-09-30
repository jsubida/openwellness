"""Google Health authorization in ``ow_api`` (opserver Phase 10.1, GHA-01).

Three routes, all under the edge group ``/api/googleHealth`` (D-05):

- ``POST /api/googleHealth/links``: staff mint a participant-bound link.
  Router-level ``require_write_principal`` plus the ``admin`` role.
- ``GET /api/googleHealth/authorize`` and ``GET /api/googleHealth/finishAuth``:
  the participant's browser, unauthenticated by design. Each carries the
  ``x-allow-unauthenticated`` marker; the link and state tokens are their
  credentials (D-11).

The routes read ``app.state.google_health_deps``, built in the lifespan by
:func:`build_google_health_deps`. While a required setting is unset or
invalid every route answers 503 with a generic page.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from ..deps.principal import ALLOW_UNAUTHENTICATED, require_write_principal
from ..event_handlers.celery_producer import CeleryTaskPublisher, ProducerSettings
from ..event_handlers.mongo_readers import MongoParticipantReader
from ..event_handlers.ports import TaskPublisher
from .google_client import GoogleOAuthClient, RequestsGoogleOAuthClient
from .oauth import (
    GoogleHealthDeps,
    authorize,
    create_link,
    finish_auth,
    get_google_health_deps,
)
from .settings import GoogleHealthSettings
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
) -> GoogleHealthDeps:
    """Production deps over the shared Mongo handle and Redis client.

    Logs one WARNING naming unset keys, never a value; while any is unset
    every Google Health route answers 503.
    """
    gh_settings = settings if settings is not None else GoogleHealthSettings()
    missing = gh_settings.missing_keys()
    if missing:
        logger.warning("googleHealth routes disabled until set: %s", ", ".join(missing))
    return GoogleHealthDeps(
        settings=gh_settings,
        tokens=GoogleHealthTokens(gh_settings, redis),
        store=GoogleHealthStore(db),
        participants=MongoParticipantReader(db),
        google=google if google is not None else RequestsGoogleOAuthClient(gh_settings),
        publisher=publisher if publisher is not None else CeleryTaskPublisher(producer_settings),
        disabled=tuple(missing),
    )
