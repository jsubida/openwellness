"""Each domain/adapter exception maps to the right AIP-193 status."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openwellness_core.adapters.exceptions import LimitExceededException
from openwellness_core.domain.exceptions.domain_exception import (
    DomainException,
    EntityNotFoundException,
    NotFound,
    UnexpectedCount,
)

from openwellness_api.errors.handlers import register_exception_handlers


@pytest.fixture
def trip_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/not-found")
    def _nf() -> None:
        raise NotFound("nope")

    @app.get("/raise/entity-not-found")
    def _enf() -> None:
        raise EntityNotFoundException("nope")

    @app.get("/raise/unexpected-count")
    def _uc() -> None:
        raise UnexpectedCount("count", expected=1, actual=3, results=[1, 2, 3])

    @app.get("/raise/limit-exceeded")
    def _le() -> None:
        raise LimitExceededException("too many", retry_after_secs=42)

    @app.get("/raise/domain-base")
    def _db() -> None:
        raise DomainException("boom")

    return app


def test_not_found_maps_to_404(trip_app: FastAPI) -> None:
    client = TestClient(trip_app)
    r = client.get("/raise/not-found")
    assert r.status_code == 404
    assert r.json()["error"]["status"] == "NOT_FOUND"


def test_entity_not_found_maps_to_404(trip_app: FastAPI) -> None:
    client = TestClient(trip_app)
    r = client.get("/raise/entity-not-found")
    assert r.status_code == 404
    assert r.json()["error"]["status"] == "NOT_FOUND"


def test_unexpected_count_maps_to_500(trip_app: FastAPI) -> None:
    client = TestClient(trip_app)
    r = client.get("/raise/unexpected-count")
    assert r.status_code == 500
    assert r.json()["error"]["status"] == "INTERNAL"


def test_limit_exceeded_maps_to_429_with_retry_after(trip_app: FastAPI) -> None:
    client = TestClient(trip_app)
    r = client.get("/raise/limit-exceeded")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "42"
    assert r.json()["error"]["status"] == "RESOURCE_EXHAUSTED"


def test_domain_base_maps_to_500(trip_app: FastAPI) -> None:
    client = TestClient(trip_app)
    r = client.get("/raise/domain-base")
    assert r.status_code == 500
    assert r.json()["error"]["status"] == "INTERNAL"
