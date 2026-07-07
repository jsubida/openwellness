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
    model_config = SettingsConfigDict(env_prefix="SYNC_GATEWAY_", extra="ignore")

    url: str = "http://localhost:4984/openwellness"

    def get_url(self) -> str:
        return self.url


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
