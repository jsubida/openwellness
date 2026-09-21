"""HTTP proof for DATA-04/R-10 write-route authentication enforcement."""

from __future__ import annotations

import pytest

from openwellness_core.application.repositories import WeightRepository


def _weight_repo(fakes):
    return fakes[WeightRepository]


@pytest.mark.parametrize(
    ("headers", "expected"),
    [({}, 401), ({"X-Principal-Id": "system:nightly-sync"}, 403),
     ({"X-Principal-Id": "coach-alice"}, 403), ({"X-Principal-Id": ""}, 403)],
)
def test_write_rejects_missing_or_client_supplied_principal(
    client, fakes, headers, expected
):
    response = client.post(
        "/v1/users/user-1/weights", json={"weight": 180.5}, headers=headers
    )
    assert response.status_code == expected, response.text
    assert _weight_repo(fakes).actor_log == []


def test_read_is_not_guarded(client):
    response = client.get("/v1/users/user-1/weights")
    assert response.status_code not in {401, 403}


@pytest.mark.parametrize(
    "path",
    [
        "/v1/auth:sendLoginCode",
        "/v1/auth:verifyLoginCode",
        "/v1/auth:sendRegistrationCode",
        "/v1/auth:verifyRegistrationCode",
        "/v1/auth:refreshToken",
        "/v1/auth:revokeToken",
    ],
)
def test_auth_routes_are_reachable_without_principal(client, path):
    response = client.post(path, json={})
    assert response.status_code not in {401, 403}