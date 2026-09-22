"""v1 router aggregator."""

from fastapi import APIRouter, Depends

from . import auth
from .deps.principal import require_write_principal
from .resources import RESOURCE_MODULES


def build_v1_router() -> APIRouter:
    # The test fixture composes the app from this builder and never calls
    # create_app(), so the write guard belongs here to avoid a false-green suite.
    v1 = APIRouter(
        prefix="/v1", dependencies=[Depends(require_write_principal)]
    )
    for mod in RESOURCE_MODULES:
        v1.include_router(mod.build_router())
    # ``auth`` is a feature module (custom-method endpoints), not an entity
    # resource — it stays out of RESOURCE_MODULES and isn't @inject-wired.
    v1.include_router(auth.build_router())
    return v1
