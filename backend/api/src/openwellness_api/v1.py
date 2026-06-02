"""v1 router aggregator."""

from fastapi import APIRouter

from . import auth
from .resources import RESOURCE_MODULES


def build_v1_router() -> APIRouter:
    v1 = APIRouter(prefix="/v1")
    for mod in RESOURCE_MODULES:
        v1.include_router(mod.build_router())
    # ``auth`` is a feature module (custom-method endpoints), not an entity
    # resource — it stays out of RESOURCE_MODULES and isn't @inject-wired.
    v1.include_router(auth.build_router())
    return v1
