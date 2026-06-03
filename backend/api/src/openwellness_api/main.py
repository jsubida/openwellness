"""FastAPI app factory and entrypoint.

The lifespan builds an :class:`ApplicationContainer`, binds the concrete
``AppConfig`` to the ``app_config`` provider, opens the Couchbase
connection, and wires the resource modules so ``@inject`` markers
resolve. Routes pull repositories through container providers — no
hand-rolled ``app.state.repos`` map.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from dependency_injector import providers
from fastapi import FastAPI

from .config import APISettings, AppConfig
from .container import ApplicationContainer
from .errors.handlers import register_exception_handlers
from .resources import RESOURCE_MODULES
from .v1 import build_v1_router

_WIRED_MODULES = [mod.__name__ for mod in RESOURCE_MODULES]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = ApplicationContainer()
    container.app_config.override(providers.Object(AppConfig()))
    container.repositories.entity_repository().initialize()
    app.state.container = container
    container.wire(modules=_WIRED_MODULES)
    try:
        yield
    finally:
        try:
            container.repositories.entity_repository().cleanup()
        except Exception:  # pragma: no cover - shutdown best-effort
            pass
        container.unwire()


def create_app() -> FastAPI:
    settings = APISettings()
    app = FastAPI(title=settings.title, lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(build_v1_router())

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    _ = healthz
    return app


app = create_app()
