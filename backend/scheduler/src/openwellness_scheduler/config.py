"""Scheduler service configuration.

Implements ``openwellness_core.infrastructure.config.AppConfigInterface``
so it can be passed straight to the core drivers — exactly like the API's
``AppConfig`` — and adds the Celery-specific knobs the API has no use for.

In Clean Architecture terms this is a *Frameworks & Drivers* detail: it
binds the abstract config ports the inner rings depend on to concrete
environment-backed settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from openwellness_core.infrastructure.config import (
    CouchbaseSettings,
    MongoSettings,
    PostgresSettings,
    StorageBackendSettings,
    SyncGatewaySettings,
)
from openwellness_core.infrastructure.config.app_config import AppConfigInterface


class AppConfig(AppConfigInterface):
    """Concrete config — composes core's protocol-typed sub-settings."""

    def __init__(self) -> None:
        self._storage = StorageBackendSettings()
        self._couchbase = CouchbaseSettings()
        self._sync_gateway = SyncGatewaySettings()
        self._mongo = MongoSettings()
        if self._storage.storage_backend == "postgres":
            self._postgres = PostgresSettings()
            if not self._postgres.url:
                raise ValueError(
                    "STORAGE_BACKEND=postgres requires POSTGRES_URL to be set"
                )
        else:
            # Don't parse POSTGRES_* env vars when Postgres isn't selected —
            # a malformed value (e.g. non-int POSTGRES_POOL_SIZE) shouldn't
            # crash startup on the couchbase-mongo path.
            self._postgres = PostgresSettings(url="", pool_size=5)

    @property
    def couchbase(self) -> CouchbaseSettings:
        return self._couchbase

    @property
    def sync_gateway(self) -> SyncGatewaySettings:
        return self._sync_gateway

    @property
    def mongo(self) -> MongoSettings:
        return self._mongo

    @property
    def postgres(self) -> PostgresSettings:
        return self._postgres

    @property
    def storage_backend(self) -> str:
        return self._storage.storage_backend


class CelerySettings(BaseSettings):
    """Broker/result-backend knobs (not part of the core config interface)."""

    model_config = SettingsConfigDict(env_prefix="CELERY_", extra="ignore")

    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    task_default_queue: str = "openwellness"
    timezone: str = "UTC"
