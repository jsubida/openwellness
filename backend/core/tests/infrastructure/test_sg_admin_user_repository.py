"""Unit tests for the Sync Gateway admin sync-user client and its settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import requests
from openwellness_core.application.repositories.sync_user_repository import (
    SyncUserRepository,
)
from openwellness_core.domain.models.sync_user import SyncUser
from openwellness_core.infrastructure.config.settings import SyncGatewaySettings
from openwellness_core.infrastructure.drivers.sg_admin_user_repository import (
    SGAdminUserRepository,
    SyncUserProvisioningError,
)

ADMIN = "http://sg:4985/spring"
SECRET = "pw-sentinel-9f2c"


class _Response:
    def __init__(self, status_code: int, body: Any = None) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("no JSON body")
        return self._body


@dataclass
class _Call:
    method: str
    url: str
    json: Any
    timeout: Any


@dataclass
class FakeSession:
    """Records every request and answers from a queue of responses."""

    responses: list[Any] = field(default_factory=list)
    calls: list[_Call] = field(default_factory=list)

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        self.calls.append(_Call(method, url, kwargs.get("json"), kwargs.get("timeout")))
        answer = self.responses.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


def _repo(*responses: Any) -> tuple[SGAdminUserRepository, FakeSession]:
    session = FakeSession(responses=list(responses))
    return SGAdminUserRepository(ADMIN, session=session, timeout=4.0), session  # type: ignore[arg-type]


def test_implements_the_sync_user_repository_interface():
    repo, _ = _repo()
    assert isinstance(repo, SyncUserRepository)


def test_provision_puts_exactly_name_password_admin_channels():
    repo, session = _repo(_Response(201, {}))
    repo.provision("c1", "c1", ["c1", "study:s", "sharedData"])
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call.method == "PUT"
    assert call.url == f"{ADMIN}/_user/c1"
    assert set(call.json) == {"name", "password", "admin_channels"}
    assert call.json == {
        "name": "c1",
        "password": "c1",
        "admin_channels": ["c1", "study:s", "sharedData"],
    }
    assert call.timeout == 4.0


@pytest.mark.parametrize("status", [200, 201])
def test_provision_accepts_create_and_update(status):
    repo, session = _repo(_Response(status, {}))
    # True only for 201: the caller then knows it created (and owns) the user.
    assert repo.provision("c1", "c1", ["c1"]) is (status == 201)
    assert len(session.calls) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 409, 500, 503])
def test_provision_other_status_raises_with_status_and_reason_never_the_password(status):
    repo, _ = _repo(_Response(status, {"error": "Bad Request", "reason": "Name mismatch"}))
    with pytest.raises(SyncUserProvisioningError) as info:
        repo.provision("user-sentinel-77", SECRET, ["c1"])
    assert info.value.status == status
    assert info.value.reason == "Name mismatch"
    text = str(info.value) + repr(info.value) + repr(info.value.args)
    assert str(status) in text
    assert "Name mismatch" in text
    assert SECRET not in text
    # Under D-14 the name IS the password, so it must not leak either.
    assert "user-sentinel-77" not in text


def test_provision_error_without_json_body_has_empty_reason():
    repo, _ = _repo(_Response(502, None))
    with pytest.raises(SyncUserProvisioningError) as info:
        repo.provision("c1", SECRET, ["c1"])
    assert info.value.status == 502
    assert info.value.reason == ""


def test_transport_error_raises_provisioning_error_without_the_url():
    repo, _ = _repo(requests.ConnectionError(f"cannot reach {ADMIN}/_user/{SECRET}"))
    with pytest.raises(SyncUserProvisioningError) as info:
        repo.provision(SECRET, SECRET, ["c1"])
    assert info.value.status is None
    assert SECRET not in str(info.value)
    assert info.value.__suppress_context__ is True


def test_save_puts_name_and_admin_channels_only():
    repo, session = _repo(_Response(200, {}))
    user = SyncUser(name="c1", admin_channels=["c1", "sharedData"], all_channels=["x"])
    assert repo.save(user) is user
    call = session.calls[0]
    assert call.method == "PUT"
    assert call.url == f"{ADMIN}/_user/c1"
    assert call.json == {"name": "c1", "admin_channels": ["c1", "sharedData"]}


def test_save_failure_raises():
    repo, _ = _repo(_Response(500, {"reason": "boom"}))
    with pytest.raises(SyncUserProvisioningError):
        repo.save(SyncUser(name="c1"))


@pytest.mark.parametrize("status", [200, 404])
def test_delete_sends_delete_and_treats_200_and_404_as_success(status):
    repo, session = _repo(_Response(status, {"error": "not_found", "reason": "missing"}))
    repo.delete("c1")
    assert session.calls[0].method == "DELETE"
    assert session.calls[0].url == f"{ADMIN}/_user/c1"


@pytest.mark.parametrize("status", [400, 500])
def test_delete_other_status_raises(status):
    repo, _ = _repo(_Response(status, {"reason": "nope"}))
    with pytest.raises(SyncUserProvisioningError) as info:
        repo.delete("c1")
    assert info.value.status == status


def test_get_by_id_404_is_none():
    repo, session = _repo(_Response(404, {"error": "not_found", "reason": "missing"}))
    assert repo.get_by_id("c1") is None
    assert session.calls[0].method == "GET"
    assert session.calls[0].url == f"{ADMIN}/_user/c1"


def test_get_by_id_200_is_a_sync_user_ignoring_unknown_keys():
    repo, _ = _repo(
        _Response(
            200,
            {
                "name": "c1",
                "admin_channels": ["c1", "sharedData", "study:s"],
                "all_channels": ["!", "c1", "sharedData", "study:s"],
                "email": "",
                "disabled": False,
            },
        )
    )
    user = repo.get_by_id("c1")
    assert isinstance(user, SyncUser)
    assert user.name == "c1"
    assert user.admin_channels == ["c1", "sharedData", "study:s"]
    assert user.all_channels == ["!", "c1", "sharedData", "study:s"]


def test_get_by_id_other_status_raises():
    repo, _ = _repo(_Response(500, {"reason": "boom"}))
    with pytest.raises(SyncUserProvisioningError):
        repo.get_by_id("c1")


def test_names_are_url_quoted():
    repo, session = _repo(_Response(201, {}), _Response(200, {}), _Response(404, None))
    repo.provision("a/b c?d", "p", ["x"])
    repo.delete("a/b c?d")
    repo.get_by_id("a/b c?d")
    for call in session.calls:
        assert call.url == f"{ADMIN}/_user/a%2Fb%20c%3Fd"


def test_trailing_slash_on_admin_db_url_is_ignored():
    session = FakeSession(responses=[_Response(201, {})])
    repo = SGAdminUserRepository(f"{ADMIN}/", session=session)  # type: ignore[arg-type]
    repo.provision("c1", "c1", [])
    assert session.calls[0].url == f"{ADMIN}/_user/c1"


# --- SyncGatewaySettings ---------------------------------------------------


def test_admin_db_url_joins_admin_url_and_db():
    settings = SyncGatewaySettings(admin_url="http://h:4985/", db="spring")
    assert settings.admin_db_url() == "http://h:4985/spring"


def test_admin_settings_read_frames_env_keys(monkeypatch):
    monkeypatch.setenv("SYNC_GATEWAY_ADMIN_URL", "http://sg-vm:4985")
    monkeypatch.setenv("SYNC_GATEWAY_DB", "spring")
    settings = SyncGatewaySettings()
    assert settings.admin_url == "http://sg-vm:4985"
    assert settings.db == "spring"
    assert settings.admin_db_url() == "http://sg-vm:4985/spring"


@pytest.mark.parametrize(
    ("admin_url", "db", "missing"),
    [
        ("", "spring", "SYNC_GATEWAY_ADMIN_URL"),
        ("http://h:4985", "", "SYNC_GATEWAY_DB"),
        ("  ", "spring", "SYNC_GATEWAY_ADMIN_URL"),
    ],
)
def test_empty_admin_url_or_db_raises_only_when_called(admin_url, db, missing, monkeypatch):
    monkeypatch.delenv("SYNC_GATEWAY_ADMIN_URL", raising=False)
    monkeypatch.delenv("SYNC_GATEWAY_DB", raising=False)
    settings = SyncGatewaySettings(admin_url=admin_url, db=db)  # constructing never raises
    with pytest.raises(ValueError, match=missing):
        settings.admin_db_url()


def test_existing_url_behaviour_is_unchanged(monkeypatch):
    monkeypatch.delenv("SYNC_GATEWAY_URL", raising=False)
    settings = SyncGatewaySettings()
    assert settings.url == "http://localhost:4984/openwellness"
    assert settings.get_url() == settings.url
