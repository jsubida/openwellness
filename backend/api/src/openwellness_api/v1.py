"""v1 router aggregator."""

from fastapi import APIRouter

from .resources import RESOURCE_MODULES


def build_v1_router() -> APIRouter:
    v1 = APIRouter(prefix="/v1")
    for mod in RESOURCE_MODULES:
        v1.include_router(mod.build_router())
    return v1
