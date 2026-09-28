"""Shared pydantic-settings classes for the Couchbase/Mongo/Postgres backends.

Defined once here so API and scheduler never drift out of sync on env var
names, prefixes, or defaults — each service's own ``config.py`` imports these
rather than redefining them.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class CouchbaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COUCHBASE_", extra="ignore")

    url: str = "couchbase://localhost"
    username: str = "Administrator"
    password: str = "password"
    bucket_name: str = "openwellness"


class SyncGatewaySettings(BaseSettings):
    """Sync Gateway endpoints.

    ``url`` is the database URL the entity driver uses. ``admin_url`` and
    ``db`` locate the admin interface (``:4985``) for sync-user provisioning.
    They read ``SYNC_GATEWAY_ADMIN_URL`` and ``SYNC_GATEWAY_DB``: the keys
    frame's ``couchbase-admin.js`` and the integration harness already use, so
    a deployment passes frame's known-good values straight through.
    """

    model_config = SettingsConfigDict(env_prefix="SYNC_GATEWAY_", extra="ignore")

    url: str = "http://localhost:4984/openwellness"
    admin_url: str = ""
    db: str = ""

    def get_url(self) -> str:
        return self.url

    def admin_db_url(self) -> str:
        """Join ``admin_url`` and ``db`` the way frame's ``baseSGUrl`` does.

        Raises ``ValueError`` naming the missing key when either is empty.
        Evaluated only when called, so an unset key never blocks boot.
        """
        missing = [
            key
            for key, value in (
                ("SYNC_GATEWAY_ADMIN_URL", self.admin_url),
                ("SYNC_GATEWAY_DB", self.db),
            )
            if not value.strip()
        ]
        if missing:
            raise ValueError(f"Sync Gateway admin settings not set: {', '.join(missing)}")
        return f"{self.admin_url.strip().rstrip('/')}/{self.db.strip().strip('/')}"


class MongoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONGO_", extra="ignore")

    url: str = "mongodb://localhost:27017"
    db: str = "openwellness"

    def get_url(self) -> str:
        return self.url


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    url: str = ""
    pool_size: int = 5

    def get_url(self) -> str:
        return self.url


class StorageBackendSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    storage_backend: Literal["couchbase-mongo", "postgres"] = "couchbase-mongo"
