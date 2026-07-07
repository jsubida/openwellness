"""Env prefix pickup and defaults for the shared settings classes."""

import pytest
from openwellness_core.infrastructure.config.settings import (
    CouchbaseSettings,
    MongoSettings,
    PostgresSettings,
    StorageBackendSettings,
    SyncGatewaySettings,
)
from pydantic import ValidationError


def test_couchbase_settings_defaults():
    settings = CouchbaseSettings()
    assert settings.url == "couchbase://localhost"
    assert settings.username == "Administrator"
    assert settings.password == "password"
    assert settings.bucket_name == "openwellness"


def test_couchbase_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("COUCHBASE_URL", "couchbase://example")
    monkeypatch.setenv("COUCHBASE_USERNAME", "user")
    monkeypatch.setenv("COUCHBASE_PASSWORD", "pass")
    monkeypatch.setenv("COUCHBASE_BUCKET_NAME", "bucket")
    settings = CouchbaseSettings()
    assert settings.url == "couchbase://example"
    assert settings.username == "user"
    assert settings.password == "pass"
    assert settings.bucket_name == "bucket"


def test_sync_gateway_settings_defaults():
    settings = SyncGatewaySettings()
    assert settings.url == "http://localhost:4984/openwellness"
    assert settings.get_url() == settings.url


def test_sync_gateway_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("SYNC_GATEWAY_URL", "http://example/sg")
    settings = SyncGatewaySettings()
    assert settings.get_url() == "http://example/sg"


def test_mongo_settings_defaults():
    settings = MongoSettings()
    assert settings.url == "mongodb://localhost:27017"
    assert settings.db == "openwellness"
    assert settings.get_url() == settings.url


def test_mongo_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://example:27017")
    monkeypatch.setenv("MONGO_DB", "otherdb")
    settings = MongoSettings()
    assert settings.get_url() == "mongodb://example:27017"
    assert settings.db == "otherdb"


def test_postgres_settings_defaults():
    settings = PostgresSettings()
    assert settings.url == ""
    assert settings.pool_size == 5
    assert settings.get_url() == ""


def test_postgres_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("POSTGRES_URL", "postgresql://example/db")
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "10")
    settings = PostgresSettings()
    assert settings.get_url() == "postgresql://example/db"
    assert settings.pool_size == 10


def test_storage_backend_settings_default():
    settings = StorageBackendSettings()
    assert settings.storage_backend == "couchbase-mongo"


def test_storage_backend_settings_accepts_postgres(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    settings = StorageBackendSettings()
    assert settings.storage_backend == "postgres"


def test_storage_backend_settings_rejects_arbitrary_value(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    with pytest.raises(ValidationError):
        StorageBackendSettings()
