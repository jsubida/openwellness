"""hapi's 404 for every other URI under the Sync Gateway prefix (EDGE-02).

Edge sends the whole ``/api/eventHandlers`` prefix (bar ActiGraph and CPAP)
to one upstream, so ow must answer every URI there exactly as frame does.
Frame (hapi) answers an unknown path, a trailing slash and a wrong method
with the same 404; FastAPI on its own would answer 307 (``redirect_slashes``)
or 405. Each case below was captured live from frame (hapi 21.4.10, ``api``
``6706a1e5``) straight to ``api:3000``: 404, the body below,
``application/json; charset=utf-8``, the eight hapi headers, no ``location``.

Uses the shared ``client`` fixture, which mounts the event-handler router as
``create_app()`` does.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from openwellness_api.main import create_app

NOT_FOUND = b'{"statusCode":404,"error":"Not Found","message":"Not Found"}'
JSON_UTF8 = "application/json; charset=utf-8"
ROUTE = "/api/eventHandlers/fitbitHeartRecord"
CATCH_ALL = "/api/eventHandlers{rest:path}"

EXPECTED_HAPI_HEADERS = {
    "vary": "origin",
    "access-control-expose-headers": "WWW-Authenticate,Server-Authorization",
    "strict-transport-security": "max-age=15768000",
    "x-frame-options": "DENY",
    "x-xss-protection": "0",
    "x-download-options": "noopen",
    "x-content-type-options": "nosniff",
    "cache-control": "no-cache",
}


def _assert_hapi_404(resp: Any) -> None:
    assert resp.status_code == 404
    assert resp.content == NOT_FOUND
    assert resp.headers["content-type"] == JSON_UTF8
    assert resp.headers["content-length"] == str(len(NOT_FOUND))
    assert "location" not in resp.headers
    for name, value in EXPECTED_HAPI_HEADERS.items():
        assert resp.headers.get(name) == value, name


@pytest.mark.parametrize(
    "path",
    [
        "/api/eventHandlers/unknown",
        "/api/eventHandlers",
        "/api/eventHandlers/",
        "/api/eventHandlers/fitbitHeartRecord/",
        "/api/eventHandlersX",
        "/api/eventHandlers/unknown/deeper",
    ],
)
def test_post_to_any_other_sg_prefix_uri_is_hapi_404(
    client: TestClient, path: str
) -> None:
    resp = client.post(
        path,
        content=b'{"studyId":"s1"}',
        headers={"content-type": "application/json"},
        follow_redirects=False,
    )
    _assert_hapi_404(resp)


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_wrong_method_on_a_real_route_is_hapi_404_not_405(
    client: TestClient, method: str
) -> None:
    resp = client.request(method, ROUTE, follow_redirects=False)
    _assert_hapi_404(resp)


def test_head_on_a_real_route_is_404(client: TestClient) -> None:
    resp = client.head(ROUTE, follow_redirects=False)
    assert resp.status_code == 404
    assert "location" not in resp.headers


def test_the_real_route_still_answers_first(client: TestClient) -> None:
    resp = client.post(
        ROUTE, content=b"{}", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 400
    assert resp.content == (
        b'{"statusCode":400,"error":"Bad Request","message":"Missing studyId"}'
    )


def test_event_fakes_are_the_routes_deps(client: TestClient, event_fakes: Any) -> None:
    event_fakes.settings.rows[("s1", 2)] = {
        "studyId": "s1",
        "fitbitHeartObserver": "jobs.fitbit.heart",
    }

    resp = client.post(
        ROUTE,
        content=b'{"studyId":"s1","owner":"o1"}',
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 204
    assert event_fakes.publisher.calls == [("jobs.fitbit.heart", ["o1"])]


def test_create_app_registers_the_catch_all_after_the_real_route() -> None:
    paths = [route.path for route in create_app().routes if isinstance(route, APIRoute)]

    assert ROUTE in paths
    assert CATCH_ALL in paths
    assert paths.index(CATCH_ALL) > paths.index(ROUTE)
    # Nothing under the prefix is registered after the catch-all.
    tail = paths[paths.index(CATCH_ALL) + 1 :]
    assert not [p for p in tail if p.startswith("/api/eventHandlers")]


def test_catch_all_is_unauthenticated_and_hidden_from_the_schema() -> None:
    from openwellness_api.deps.principal import ALLOW_UNAUTHENTICATED

    route = next(
        r
        for r in create_app().routes
        if isinstance(r, APIRoute) and r.path == CATCH_ALL
    )
    assert (route.openapi_extra or {}).get(ALLOW_UNAUTHENTICATED) is True
    assert route.include_in_schema is False
    assert route.methods == {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
