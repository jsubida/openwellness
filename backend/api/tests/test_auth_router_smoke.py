"""Wiring smoke tests for the email-OTP auth router.

These prove the HTTP path is connected end-to-end: the six custom-method routes
register at the exact ``/v1/auth:<verb>`` paths, a happy-path login send→verify
issues a credential, and an unknown email still returns the uniform 200 (no
enumeration leak). The full endpoint matrix (anti-enumeration edge cases, 429
lockouts, refresh reuse, etc.) is a later task — this only validates the wiring.
"""

from __future__ import annotations

from typing import Any

import redis.exceptions
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient

_EXPECTED_PATHS = {
    "/v1/auth:sendLoginCode",
    "/v1/auth:verifyLoginCode",
    "/v1/auth:sendRegistrationCode",
    "/v1/auth:verifyRegistrationCode",
    "/v1/auth:refreshToken",
    "/v1/auth:revokeToken",
}


def test_route_paths_registered(app: FastAPI) -> None:
    paths = {getattr(r, "path", "") for r in app.routes}
    missing = _EXPECTED_PATHS - paths
    assert not missing, f"missing auth routes: {missing}"


def test_login_send_then_verify_happy_path(
    client: TestClient,
    seed_accounts: dict[str, Any],
    fake_email_sender: Any,
) -> None:
    email = seed_accounts["login_email"]

    send = client.post("/v1/auth:sendLoginCode", json={"email": email})
    assert send.status_code == 200, send.text
    send_body = send.json()
    assert send_body["status"] == "OK"
    assert "expiresInSeconds" in send_body
    assert "resendAfterSeconds" in send_body

    code = fake_email_sender.last_code(email)
    assert code is not None, "no OTP code recorded for the seeded login email"

    verify = client.post(
        "/v1/auth:verifyLoginCode", json={"email": email, "code": code}
    )
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["accessToken"]
    assert body["tokenType"] == "Bearer"
    assert body["refreshToken"]
    assert body["principal"]["userId"] == seed_accounts["login_user_id"]
    assert body["principal"]["participant"] == (
        f"participants/{seed_accounts['login_pid']}"
    )


def test_unknown_email_uniform_200(
    client: TestClient,
    seed_accounts: dict[str, Any],
    fake_email_sender: Any,
) -> None:
    unknown = "nobody@example.com"

    resp = client.post("/v1/auth:sendLoginCode", json={"email": unknown})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "OK"
    assert "expiresInSeconds" in body
    assert "resendAfterSeconds" in body

    # Nothing was actually delivered for an ineligible address.
    assert fake_email_sender.last_code(unknown) is None
    assert all(e != unknown for (e, _c, _p) in fake_email_sender.sent)


class _DeadRedisOtpStore:
    """Stand-in OTP store whose first call simulates a Redis outage.

    ``AuthService.send_login_code`` calls ``check_send_limits`` first (before any
    eligibility lookup), so raising a ``redis.exceptions.ConnectionError`` here
    is exactly what a runtime Redis outage looks like from the service's vantage
    point: a ``RedisError`` propagating out of the request handler. This drives
    the registered ``RedisError`` handler, which must map it to a clean 503
    rather than a 500. We intentionally use a stub (not a real ``RedisOtpStore``
    pointed at a dead port) because ``RedisOtpStore.__init__`` runs a
    ``decode_responses`` probe (``set``/``get``) that would raise at construction
    time — before the request — so it would not exercise the request-time path.
    """

    def check_send_limits(self, **_kwargs: Any) -> None:
        raise redis.exceptions.ConnectionError("redis is down")


def test_redis_down_returns_503(client: TestClient) -> None:
    """A runtime Redis outage maps to a clean AIP-193 503 (UNAVAILABLE)."""
    # Override the live auth container's otp_store BEFORE the request so the
    # per-request ``auth_service_dep`` assembles the service with the dead store.
    client.app.state.auth_container.otp_store.override(
        providers.Object(_DeadRedisOtpStore())
    )
    try:
        resp = client.post(
            "/v1/auth:sendLoginCode", json={"email": "x@example.com"}
        )
    finally:
        client.app.state.auth_container.otp_store.reset_override()

    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["error"]["status"] == "UNAVAILABLE"
