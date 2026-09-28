"""Native event-handler routes: Sync Gateway and vendor webhooks.

These are permanent, externally registered contracts. Sync Gateway's
``document_changed`` webhooks (and later ActiGraph) call these exact paths
through the edge route table, so they live in their own package and never
under ``compat/``.

They are unauthenticated by design, matching frame's ``auth: false``. Each
route opts out of the write guard with the per-route
``openapi_extra={"x-allow-unauthenticated": True}`` marker that the
route-walking test checks; there is no path allowlist.

Responses are byte-for-byte hapi parity (D-05): the same status codes,
bodies and headers frame sends, so a caller cannot tell which side answered
and a flip back to frame is a pure route change.
"""

from __future__ import annotations

import logging
from typing import Any, Final

from fastapi import APIRouter, Response

from ..deps.principal import ALLOW_UNAUTHENTICATED
from .celery_producer import CeleryTaskPublisher, ProducerSettings
from .couchbase_views import CouchbaseViewSettingsReader
from .hapi import boom
from .mongo_readers import MongoStudyReader
from .ports import EventHandlerDeps
from .sync_gateway import PREFIX, build_sync_gateway_router

logger = logging.getLogger(__name__)

# One pattern covers the bare prefix, a trailing slash, any sub-path and an
# adjacent name such as ``/api/eventHandlersX``: Starlette compiles a path
# parameter directly after a literal segment, and the ``path`` convertor
# matches the empty string.
CATCH_ALL_PATH: Final = PREFIX + "{rest:path}"
CATCH_ALL_METHODS: Final = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


async def _hapi_not_found(rest: str) -> Response:
    """hapi's 404 for any URI under the prefix with no matching route.

    Registered after every real route, so Starlette reaches it only when no
    route matches path and method. That turns FastAPI's 307 trailing-slash
    redirect and 405 wrong-method answers into frame's 404.
    """
    return boom(404, "Not Found")


def build_event_handlers_router() -> APIRouter:
    router = APIRouter()
    router.include_router(build_sync_gateway_router())
    # Must stay last: every real event route has to be matched before it.
    router.api_route(
        CATCH_ALL_PATH,
        methods=CATCH_ALL_METHODS,
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
        include_in_schema=False,
        name="eventHandlersNotFound",
    )(_hapi_not_found)
    return router


def build_event_handler_deps(
    *, bucket: Any, db: Any, producer_settings: ProducerSettings
) -> EventHandlerDeps:
    """Production deps: frame's view, frame's ``studies`` collection, Celery.

    ``bucket`` is the Couchbase SDK bucket of the already-initialized entity
    repository; ``db`` is the Mongo collection repository. Logs one WARNING,
    naming only the key, when the broker URL is empty: the app still serves,
    and every publish fails as a hapi 500 until the key is set.
    """
    if not producer_settings.broker_url:
        logger.warning(
            "CELERY_BROKER_URL is not set; event-handler task publishing will fail"
        )
    return EventHandlerDeps(
        settings=CouchbaseViewSettingsReader(bucket),
        studies=MongoStudyReader(db),
        publisher=CeleryTaskPublisher(producer_settings),
    )
