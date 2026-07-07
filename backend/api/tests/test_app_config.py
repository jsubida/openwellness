"""AppConfig storage backend selection and fail-fast validation."""

import pytest
from openwellness_api.config import AppConfig
from pydantic import ValidationError


def test_default_backend_constructs_cleanly(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    config = AppConfig()

    assert config.storage_backend == "couchbase-mongo"


def test_postgres_backend_without_url_raises(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    with pytest.raises(ValueError, match="POSTGRES_URL"):
        AppConfig()


def test_postgres_backend_with_url_constructs_cleanly(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://example/db")

    config = AppConfig()

    assert config.storage_backend == "postgres"
    assert config.postgres.get_url() == "postgresql://example/db"


def test_invalid_backend_value_raises_validation_error(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "nonsense")

    with pytest.raises(ValidationError):
        AppConfig()


def test_default_backend_ignores_malformed_postgres_env(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("POSTGRES_POOL_SIZE", "not-an-int")

    config = AppConfig()

    assert config.storage_backend == "couchbase-mongo"
