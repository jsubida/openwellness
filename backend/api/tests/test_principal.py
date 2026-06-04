"""Unit tests for the JWT-aware ``get_principal`` + strict ``require_principal``.

These exercise the backwards-compatible principal swap directly (no HTTP
stack): a lightweight fake ``Request`` supplies ``.headers``, ``.url.path``,
and ``.app.state.auth_container``. Valid-bearer cases mint a REAL access JWT
via a real :class:`JwtTokenService` (PyJWT is never mocked).

Top priority is the never-raise contract of ``get_principal`` (a malformed
bearer must degrade to anonymous, NOT 401) and the enforce-gated 401 that may
only originate in ``require_principal``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from openwellness_api.config import AuthSettings
from openwellness_api.auth.token_service import JwtTokenService
from openwellness_api.deps.principal import (
    Principal,
    get_principal,
    require_principal,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeUrl:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeState:
    """Stand-in for ``request.app.state``; only attributes set are present."""


class _FakeApp:
    def __init__(self, state: _FakeState) -> None:
        self.state = state


class _FakeRequest:
    """Minimal Request: case-insensitive ``.headers``, ``.url.path``, ``.app``."""

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        *,
        auth_container: Any | _Unset = None,
        path: str = "/v1/test",
    ) -> None:
        self.headers = Headers(headers or {})
        self.url = _FakeUrl(path)
        state = _FakeState()
        if not isinstance(auth_container, _Unset):
            state.auth_container = auth_container  # type: ignore[attr-defined]
        self.app = _FakeApp(state)


class _Unset:
    """Sentinel so a test can build a request whose state has NO auth_container."""


_NO_CONTAINER = _Unset()


def _settings() -> AuthSettings:
    return AuthSettings(
        jwt_secret="x" * 40,
        jwt_issuer="openwellness-api",
        jwt_audience="openwellness-api",
    )


class _FakeAuthContainer:
    """Exposes ``token_service()`` and ``auth_settings()`` like the real one."""

    def __init__(
        self,
        token_service: JwtTokenService | None = None,
        enforce_principal: bool = False,
    ) -> None:
        self._token_service = token_service or JwtTokenService(
            settings=_settings(), clock=lambda: datetime.now(timezone.utc)
        )
        # Mirror _settings() so the container's auth_settings can't silently
        # diverge from the token_service's signing/validation settings.
        self._settings = AuthSettings(
            jwt_secret="x" * 40,
            jwt_issuer="openwellness-api",
            jwt_audience="openwellness-api",
            enforce_principal=enforce_principal,
        )

    def token_service(self) -> JwtTokenService:
        return self._token_service

    def auth_settings(self) -> AuthSettings:
        return self._settings


def _mint(
    svc: JwtTokenService,
    *,
    user_id: str,
    participant: str | None = None,
    roles: list[str] | None = None,
) -> str:
    return svc.mint_access(
        user_id=user_id, participant=participant, roles=roles or []
    )


# --------------------------------------------------------------------------- #
# Principal additive defaults
# --------------------------------------------------------------------------- #
def test_principal_additive_defaults() -> None:
    p = Principal(id="u")
    assert p.id == "u"
    assert p.roles == ()
    assert p.participant is None
    assert p.is_authenticated is False


def test_principal_full_construction() -> None:
    p = Principal(
        id="u", roles=("participant",), participant="p1", is_authenticated=True
    )
    assert p.id == "u"
    assert p.roles == ("participant",)
    assert p.participant == "p1"
    assert p.is_authenticated is True


# --------------------------------------------------------------------------- #
# get_principal — anonymous / legacy paths (never raises)
# --------------------------------------------------------------------------- #
def test_get_principal_x_principal_id_no_bearer() -> None:
    req = _FakeRequest({"X-Principal-Id": "caller-1"})
    p = get_principal(req, x_principal_id="caller-1")  # type: ignore[arg-type]
    assert p == Principal(id="caller-1", is_authenticated=False)
    assert p.is_authenticated is False


def test_get_principal_no_headers_is_anonymous() -> None:
    req = _FakeRequest({})
    p = get_principal(req, x_principal_id=None)  # type: ignore[arg-type]
    assert p == Principal(id="anonymous", is_authenticated=False)


# --------------------------------------------------------------------------- #
# get_principal — valid bearer (real JWT round-trip)
# --------------------------------------------------------------------------- #
def test_get_principal_valid_bearer_is_authenticated() -> None:
    svc = JwtTokenService(
        settings=_settings(), clock=lambda: datetime.now(timezone.utc)
    )
    token = _mint(svc, user_id="U1", participant="P1", roles=["participant"])
    container = _FakeAuthContainer(token_service=svc)
    req = _FakeRequest(
        {"Authorization": f"Bearer {token}"}, auth_container=container
    )

    p = get_principal(req, x_principal_id=None)  # type: ignore[arg-type]

    assert p == Principal(
        id="U1",
        participant="P1",
        roles=("participant",),
        is_authenticated=True,
    )


# --------------------------------------------------------------------------- #
# get_principal — failure paths NEVER raise (degrade to anonymous)
# --------------------------------------------------------------------------- #
def test_get_principal_garbage_bearer_falls_back_no_raise() -> None:
    svc = JwtTokenService(
        settings=_settings(), clock=lambda: datetime.now(timezone.utc)
    )
    container = _FakeAuthContainer(token_service=svc)
    req = _FakeRequest(
        {"Authorization": "Bearer not.a.jwt", "X-Principal-Id": "caller-1"},
        auth_container=container,
    )

    p = get_principal(req, x_principal_id="caller-1")  # type: ignore[arg-type]

    assert p == Principal(id="caller-1", is_authenticated=False)


def test_get_principal_bearer_but_no_auth_container_falls_back() -> None:
    # app.state has NO auth_container at all → must degrade, not crash.
    svc = JwtTokenService(
        settings=_settings(), clock=lambda: datetime.now(timezone.utc)
    )
    token = _mint(svc, user_id="U1")
    req = _FakeRequest(
        {"Authorization": f"Bearer {token}"}, auth_container=_NO_CONTAINER
    )

    p = get_principal(req, x_principal_id=None)  # type: ignore[arg-type]

    assert p == Principal(id="anonymous", is_authenticated=False)


def test_get_principal_empty_bearer_token_falls_back() -> None:
    # "Authorization: Bearer" with no token after the space → anonymous, no raise.
    container = _FakeAuthContainer()
    req = _FakeRequest(
        {"Authorization": "Bearer ", "X-Principal-Id": "caller-1"},
        auth_container=container,
    )

    p = get_principal(req, x_principal_id="caller-1")  # type: ignore[arg-type]

    assert p == Principal(id="caller-1", is_authenticated=False)


def test_get_principal_expired_token_falls_back_no_raise() -> None:
    # A well-formed but EXPIRED token (minted with a clock pinned far in the
    # past so exp < real now) must degrade to anonymous, not raise.
    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    minting_svc = JwtTokenService(settings=_settings(), clock=lambda: past)
    token = _mint(minting_svc, user_id="U1", roles=["participant"])
    # Verifier uses the real wall clock → the token is long expired.
    verify_svc = JwtTokenService(
        settings=_settings(), clock=lambda: datetime.now(timezone.utc)
    )
    container = _FakeAuthContainer(token_service=verify_svc)
    req = _FakeRequest(
        {"Authorization": f"Bearer {token}", "X-Principal-Id": "caller-1"},
        auth_container=container,
    )

    p = get_principal(req, x_principal_id="caller-1")  # type: ignore[arg-type]

    assert p == Principal(id="caller-1", is_authenticated=False)


# --------------------------------------------------------------------------- #
# require_principal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("enforce", [True, False])
def test_require_principal_returns_authenticated_unchanged(enforce: bool) -> None:
    container = _FakeAuthContainer(enforce_principal=enforce)
    req = _FakeRequest({}, auth_container=container)
    authed = Principal(
        id="U1", roles=("participant",), participant="P1", is_authenticated=True
    )

    result = require_principal(req, principal=authed)  # type: ignore[arg-type]

    assert result is authed


def test_require_principal_anonymous_enforce_on_raises_401() -> None:
    container = _FakeAuthContainer(enforce_principal=True)
    req = _FakeRequest({}, auth_container=container, path="/v1/secret")
    anon = Principal(id="anonymous", is_authenticated=False)

    with pytest.raises(HTTPException) as excinfo:
        require_principal(req, principal=anon)  # type: ignore[arg-type]

    exc = excinfo.value
    assert exc.status_code == 401
    assert isinstance(exc.detail, dict)
    detail = cast("dict[str, Any]", exc.detail)
    assert detail["error"]["status"] == "UNAUTHENTICATED"
    assert detail["error"]["code"] == 401


def test_require_principal_anonymous_enforce_off_returns_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    container = _FakeAuthContainer(enforce_principal=False)
    req = _FakeRequest({}, auth_container=container, path="/v1/secret")
    anon = Principal(id="anonymous", is_authenticated=False)

    with caplog.at_level(logging.WARNING, logger="openwellness_api.deps.principal"):
        result = require_principal(req, principal=anon)  # type: ignore[arg-type]

    assert result is anon
    assert any(
        record.levelno == logging.WARNING
        and "would-be 401" in record.getMessage()
        and "/v1/secret" in record.getMessage()
        for record in caplog.records
    )


def test_require_principal_missing_auth_container_treats_enforce_false() -> None:
    # No auth_container on app.state → must not crash, must treat enforce=False.
    req = _FakeRequest({}, auth_container=_NO_CONTAINER)
    anon = Principal(id="anonymous", is_authenticated=False)

    result = require_principal(req, principal=anon)  # type: ignore[arg-type]

    assert result is anon
