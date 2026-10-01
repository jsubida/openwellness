"""Structural proof that every deployed write route is guarded.

The only unauthenticated write surface is the six ``/v1/auth:*`` routes and
the externally registered event-handler contracts (HOOK-01/02), which answer
Sync Gateway and vendor webhooks exactly as frame's ``auth: false`` routes do.
"""

from __future__ import annotations

from fastapi.dependencies.utils import get_flat_dependant
from fastapi.routing import APIRoute

from openwellness_api.deps.principal import (
    ALLOW_UNAUTHENTICATED,
    READ_ONLY,
    WRITE_METHODS,
    require_write_principal,
)
from openwellness_api.main import create_app


EXPECTED_EXEMPTIONS = {
    "/v1/auth:sendLoginCode",
    "/v1/auth:verifyLoginCode",
    "/v1/auth:sendRegistrationCode",
    "/v1/auth:verifyRegistrationCode",
    "/v1/auth:refreshToken",
    "/v1/auth:revokeToken",
    # Sync Gateway webhooks (HOOK-01) and the hapi-404 catch-all for every
    # other URI under the SG prefix.
    "/api/eventHandlers/activity",
    "/api/eventHandlers/fitbitHeartRecord",
    "/api/eventHandlers/post",
    "/api/eventHandlers/weight",
    # The ActiGraph webhook and handshake (HOOK-02, D-17: frame's trust model).
    "/api/eventHandlers/actigraph",
    "/api/eventHandlers{rest:path}",
    # The Google Health notification receiver (GHA-02). Google's subscriber
    # handshake posts once with the configured Authorization secret and once
    # without it, expecting 401, so the route checks the secret and the
    # GOOGLE-HEALTH-API-SIGNATURE itself instead of a bearer principal.
    "/api/googleHealth/notifications",
}

EVENT_HANDLER_PREFIX = "/api/eventHandlers"

# POST custom methods that only read (see READ_ONLY in deps/principal.py).
EXPECTED_READ_ONLY = {
    "/v1/conversations:search",
    "/v1/studies:lookup",
}


def _write_routes() -> list[APIRoute]:
    return [
        route
        for route in create_app().routes
        if isinstance(route, APIRoute)
        and route.methods
        and route.methods.intersection(WRITE_METHODS)
    ]


def test_every_write_route_is_guarded_or_explicitly_exempt() -> None:
    unguarded: list[str] = []
    exempt: set[str] = set()
    read_only: set[str] = set()

    for route in _write_routes():
        extra = route.openapi_extra or {}
        if extra.get(ALLOW_UNAUTHENTICATED):
            exempt.add(route.path)
            continue
        if extra.get(READ_ONLY):
            read_only.add(route.path)
            continue
        if not any(
            dependency.call is require_write_principal
            for dependency in route.dependant.dependencies
        ):
            unguarded.append(f"{sorted(route.methods)} {route.path}")

    assert unguarded == [], unguarded
    assert exempt == EXPECTED_EXEMPTIONS
    assert read_only == EXPECTED_READ_ONLY


def test_the_route_inventory_has_not_silently_shrunk() -> None:
    """The guard assertion also passes for an empty app, so count independently."""
    assert len(_write_routes()) >= 188


def test_event_handler_routes_carry_no_write_guard() -> None:
    """HOOK-02 containment: no credential dependency on an event-handler route."""
    event_routes = [
        route
        for route in create_app().routes
        if isinstance(route, APIRoute) and route.path.startswith(EVENT_HANDLER_PREFIX)
    ]
    assert event_routes, "the event-handler router is not mounted"

    guarded = [
        route.path
        for route in event_routes
        if any(
            dependency.call is require_write_principal
            for dependency in get_flat_dependant(route.dependant).dependencies
        )
        or route.dependencies
    ]
    assert guarded == []
    assert all(
        (route.openapi_extra or {}).get(ALLOW_UNAUTHENTICATED) for route in event_routes
    )
