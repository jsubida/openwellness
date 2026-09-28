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

from fastapi import APIRouter

from .sync_gateway import build_sync_gateway_router


def build_event_handlers_router() -> APIRouter:
    router = APIRouter()
    router.include_router(build_sync_gateway_router())
    return router
