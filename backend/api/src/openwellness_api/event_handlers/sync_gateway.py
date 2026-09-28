"""Sync Gateway webhook routes (interface stub; implementation follows)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..deps.principal import ALLOW_UNAUTHENTICATED


def build_sync_gateway_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/eventHandlers/fitbitHeartRecord",
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
    )
    async def fitbit_heart_record(request: Request) -> Response:
        return Response(status_code=501)

    _ = fitbit_heart_record
    return router
