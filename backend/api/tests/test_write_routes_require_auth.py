"""Structural proof that every deployed v1 write route is guarded."""

from __future__ import annotations

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
}

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