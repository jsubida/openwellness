"""``POST /api/participants``: auth chain, pre-checks, SG-first provisioning,
Mongo writes, compensation and response (plan 10-07 Task 3)."""

from __future__ import annotations

import json
import logging
from typing import Any

import bcrypt
import pytest
from bson import ObjectId
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from openwellness_api.deps.principal import ALLOW_UNAUTHENTICATED, require_write_principal
from openwellness_api.frame_participants import build_frame_participant_deps
from openwellness_api.main import create_app
from openwellness_core.infrastructure.config.settings import SyncGatewaySettings
from openwellness_core.infrastructure.drivers.sg_admin_user_repository import (
    SGAdminUserRepository,
    SyncUserProvisioningError,
)

PATH = "/api/participants"
PASSWORD = "Pw-Sentinel-3141"
USERNAME = "Sentinel_User"
EMAIL = "Sentinel.Mail@Example.com"
HAPI_JSON = "application/json; charset=utf-8"


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def _bearer(app, user_id: str, roles: tuple[str, ...] = ("admin",)) -> dict[str, str]:
    token = app.state.auth_container.token_service().mint_access(user_id=user_id, roles=roles)
    return {"Authorization": f"Bearer {token}"}


def _body(study_id: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "studyId": study_id,
        "username": USERNAME,
        "password": PASSWORD,
        "email": EMAIL,
        "participantNumber": " P-007 ",
    }
    body.update(overrides)
    return body


@pytest.fixture
def root(app, participant_fakes):
    """A root admin's headers and a seeded study id."""
    user_id = participant_fakes.seed_root_admin()
    return _bearer(app, user_id), participant_fakes.seed_study()


def _boom(resp, status: int, error: str, message: str) -> None:
    assert resp.status_code == status, resp.text
    assert resp.headers["content-type"] == HAPI_JSON
    assert resp.json() == {"statusCode": status, "error": error, "message": message}


def _nothing_happened(fakes) -> None:
    assert fakes.calls == []
    assert fakes.raw["participants"].count_documents({}) == 0
    assert fakes.sync_users.users == {}


# --- auth chain ---------------------------------------------------------------


def test_no_bearer_is_401_with_no_sg_call_and_no_write(client, participant_fakes):
    study = participant_fakes.seed_study()
    resp = client.post(PATH, json=_body(study))
    assert resp.status_code == 401
    _nothing_happened(participant_fakes)


def test_client_principal_header_is_403(client, participant_fakes):
    resp = client.post(PATH, json=_body(participant_fakes.seed_study()), headers={"X-Principal-Id": "x"})
    assert resp.status_code == 403
    _nothing_happened(participant_fakes)


def test_bearer_without_admin_role_is_hapi_insufficient_scope(app, client, participant_fakes):
    user_id = participant_fakes.seed_root_admin()
    headers = _bearer(app, user_id, roles=("participant",))
    resp = client.post(PATH, json=_body(participant_fakes.seed_study()), headers=headers)
    _boom(resp, 403, "Forbidden", "Insufficient scope")
    _nothing_happened(participant_fakes)


@pytest.mark.parametrize("groups", [{}, {"coach": "Coach"}, None])
def test_admin_not_in_root_group_is_hapi_403(app, client, participant_fakes, groups):
    headers = _bearer(app, participant_fakes.seed_admin(groups))
    resp = client.post(PATH, json=_body(participant_fakes.seed_study()), headers=headers)
    _boom(resp, 403, "Forbidden", "Missing required group membership.")
    _nothing_happened(participant_fakes)


@pytest.mark.parametrize("subject", [str(ObjectId()), "not-an-object-id"])
def test_admin_role_without_a_users_or_admins_document_is_403(app, client, participant_fakes, subject):
    resp = client.post(PATH, json=_body(participant_fakes.seed_study()), headers=_bearer(app, subject))
    _boom(resp, 403, "Forbidden", "Missing required group membership.")
    _nothing_happened(participant_fakes)


# --- payload and validation ---------------------------------------------------


def test_malformed_json_is_hapi_400(client, root, participant_fakes):
    headers, _ = root
    resp = client.post(PATH, content=b"{bad", headers={**headers, "content-type": "application/json"})
    _boom(resp, 400, "Bad Request", "Invalid request payload JSON format")
    _nothing_happened(participant_fakes)


def test_payload_parse_precedes_the_scope_check_as_in_hapi(app, client, participant_fakes):
    headers = _bearer(app, participant_fakes.seed_root_admin(), roles=("participant",))
    resp = client.post(PATH, content=b"{bad", headers={**headers, "content-type": "application/json"})
    _boom(resp, 400, "Bad Request", "Invalid request payload JSON format")


@pytest.mark.parametrize(
    "overrides",
    [{"studyId": "short"}, {"username": "bad-name"}, {"gender": 2}, {"extra": 1}, {"email": "nope"}],
)
def test_invalid_payload_is_frames_production_validation_message(client, root, participant_fakes, overrides):
    headers, study = root
    resp = client.post(PATH, json=_body(study, **overrides), headers=headers)
    _boom(resp, 400, "Bad Request", "Invalid request payload input")
    _nothing_happened(participant_fakes)


def test_validation_precedes_the_root_group_check(app, client, participant_fakes):
    headers = _bearer(app, participant_fakes.seed_admin({}))
    resp = client.post(PATH, json=_body(participant_fakes.seed_study(), gender=2), headers=headers)
    _boom(resp, 400, "Bad Request", "Invalid request payload input")


# --- pre-checks ---------------------------------------------------------------


def test_existing_username_is_409_case_insensitively(client, root, participant_fakes):
    headers, study = root
    participant_fakes.seed_user(USERNAME.lower(), "someone-else@example.org")
    resp = client.post(PATH, json=_body(study), headers=headers)
    _boom(resp, 409, "Conflict", "Username already in use.")
    _nothing_happened(participant_fakes)


def test_existing_email_is_409(client, root, participant_fakes):
    headers, study = root
    participant_fakes.seed_user("someone_else", EMAIL.lower())
    resp = client.post(PATH, json=_body(study), headers=headers)
    _boom(resp, 409, "Conflict", "Email already in use.")
    _nothing_happened(participant_fakes)


def test_unknown_study_is_404(client, root, participant_fakes):
    headers, _ = root
    resp = client.post(PATH, json=_body(str(ObjectId())), headers=headers)
    _boom(resp, 404, "Not Found", "Study not found for studyId.")
    _nothing_happened(participant_fakes)


def test_supplied_id_already_used_is_409(client, root, participant_fakes):
    headers, study = root
    taken = str(ObjectId())
    participant_fakes.seed_participant(taken)
    resp = client.post(PATH, json=_body(study, id=taken), headers=headers)
    _boom(resp, 409, "Conflict", "Participant ID already in use.")
    assert participant_fakes.calls == []
    assert participant_fakes.sync_users.users == {}


def test_uncastable_study_id_is_hapi_500_as_frames_find_by_id_throws(client, root, participant_fakes):
    headers, _ = root
    resp = client.post(PATH, json=_body("z" * 24), headers=headers)
    _boom(resp, 500, "Internal Server Error", "An internal server error occurred")
    _nothing_happened(participant_fakes)


# --- the happy path -----------------------------------------------------------


def test_valid_request_provisions_sg_first_then_writes_mongo_in_order(client, root, participant_fakes):
    headers, study = root
    resp = client.post(PATH, json=_body(study), headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == HAPI_JSON

    body = resp.json()
    pid = body["_id"]
    user_id = body["userId"]
    assert participant_fakes.calls == [
        ("sg.provision", (pid, pid, [pid, f"study:{study}", "sharedData"])),
        ("participants.insert_one", ObjectId(pid)),
        ("users.insert_one", ObjectId(user_id)),
        ("participants.update_one", ({"_id": ObjectId(pid)}, {"$set": {"userId": ObjectId(user_id)}})),
        (
            "users.update_one",
            ({"_id": ObjectId(user_id)}, {"$set": {"roles.participant": {"pid": pid, "pnum": "P-007"}}}),
        ),
    ]
    assert participant_fakes.sync_users.users[pid]["password"] == pid


def test_response_and_stored_documents_are_frame_shaped(client, root, participant_fakes):
    headers, study = root
    coach = str(ObjectId())
    resp = client.post(PATH, json=_body(study, assignedCoachId=coach, tz="America/Chicago"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    pid = body["_id"]

    stored = participant_fakes.raw["participants"].find_one({"_id": ObjectId(pid)})
    assert isinstance(stored["studyId"], ObjectId) and str(stored["studyId"]) == study
    assert isinstance(stored["userId"], ObjectId)
    assert isinstance(stored["assignedCoachId"], ObjectId)
    assert stored["couchId"] == pid
    assert stored["participantNumber"] == "P-007"
    assert stored["__v"] == 0
    for key in ("username", "password", "email", "location"):
        assert key not in stored

    user = participant_fakes.raw["users"].find_one({"_id": stored["userId"]})
    assert user["username"] == USERNAME.lower()
    assert user["email"] == EMAIL.lower()
    assert user["password"].startswith("$2b$10$")
    assert bcrypt.checkpw(PASSWORD.encode(), user["password"].encode())
    assert user["roles"] == {"participant": {"pid": pid, "pnum": "P-007"}}

    assert body["studyId"] == study
    assert body["assignedCoachId"] == coach
    assert body["userId"] == str(stored["userId"])
    assert body["timeCreated"].endswith("Z") and len(body["timeCreated"]) == 24
    assert body["user"]["_id"] == str(stored["userId"])
    assert body["user"]["roles"] == {"participant": {"pid": pid, "pnum": "P-007"}}
    # D-11 parity: frame returns the hash (research Open Question 5, flagged).
    assert body["user"]["password"] == user["password"]


def test_supplied_free_id_becomes_the_participant_id(client, root, participant_fakes):
    headers, study = root
    wanted = str(ObjectId())
    resp = client.post(PATH, json=_body(study, id=wanted), headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["_id"] == wanted
    assert resp.json()["couchId"] == wanted


# --- failures and compensation ------------------------------------------------


def test_sg_provision_failure_is_400_with_zero_mongo_writes(client, root, participant_fakes):
    headers, study = root
    participant_fakes.sync_users.fail_provision = SyncUserProvisioningError("provision", 500, "boom")
    resp = client.post(PATH, json=_body(study), headers=headers)
    _boom(resp, 400, "Bad Request", "Participant creation failed.")
    assert participant_fakes.writes() == ["sg.provision"]
    assert participant_fakes.raw["participants"].count_documents({}) == 0
    assert participant_fakes.raw["users"].count_documents({"username": USERNAME.lower()}) == 0


def test_users_insert_failure_deletes_the_participant_then_the_sg_user(client, root, participant_fakes):
    headers, study = root
    participant_fakes.fail_on[("users", "insert_one")] = DuplicateKeyError("E11000 duplicate key")
    resp = client.post(PATH, json=_body(study), headers=headers)
    _boom(resp, 400, "Bad Request", "Participant creation failed.")

    pid = participant_fakes.calls[0][1][0]
    assert participant_fakes.writes() == [
        "sg.provision",
        "participants.insert_one",
        "users.insert_one",
        "participants.delete_one",
        "sg.delete",
    ]
    assert participant_fakes.calls[-1] == ("sg.delete", pid)
    assert participant_fakes.raw["participants"].count_documents({"_id": ObjectId(pid)}) == 0
    assert participant_fakes.raw["users"].count_documents({"roles.participant.pid": pid}) == 0
    assert participant_fakes.raw["users"].count_documents({"username": USERNAME.lower()}) == 0
    assert pid not in participant_fakes.sync_users.users


@pytest.mark.parametrize("failing", [("participants", "update_one"), ("users", "update_one")])
def test_link_failure_deletes_both_documents_then_the_sg_user(client, root, participant_fakes, failing):
    headers, study = root
    participant_fakes.fail_on[failing] = RuntimeError("write failed")
    resp = client.post(PATH, json=_body(study), headers=headers)
    _boom(resp, 400, "Bad Request", "Participant creation failed.")
    pid = participant_fakes.calls[0][1][0]
    assert participant_fakes.writes()[-3:] == ["users.delete_one", "participants.delete_one", "sg.delete"]
    assert participant_fakes.raw["participants"].count_documents({"_id": ObjectId(pid)}) == 0
    assert participant_fakes.raw["users"].count_documents({"username": USERNAME.lower()}) == 0
    assert participant_fakes.sync_users.users == {}


@pytest.mark.parametrize("overrides", [{"assignedCoachId": "coach"}, {"participantNumber": "   "}])
def test_values_frame_fails_on_mid_create_fail_before_sg_or_mongo(client, root, participant_fakes, overrides):
    headers, study = root
    resp = client.post(PATH, json=_body(study, **overrides), headers=headers)
    _boom(resp, 400, "Bad Request", "Participant creation failed.")
    _nothing_happened(participant_fakes)


# --- logging ------------------------------------------------------------------


def test_logs_never_carry_password_hash_email_or_username(client, root, participant_fakes, caplog):
    headers, study = root
    caplog.set_level(logging.DEBUG)
    ok = client.post(PATH, json=_body(study), headers=headers)
    assert ok.status_code == 200
    stored_hash = ok.json()["user"]["password"]
    pid = ok.json()["_id"]

    participant_fakes.fail_on[("users", "insert_one")] = DuplicateKeyError(
        f"E11000 dup key {USERNAME.lower()} {EMAIL.lower()}"
    )
    failed = client.post(
        PATH, json=_body(study, username="Other_Name", email="other@example.org"), headers=headers
    )
    assert failed.status_code == 400
    participant_fakes.fail_on.clear()
    participant_fakes.sync_users.fail_provision = SyncUserProvisioningError("provision", 500, "boom")
    client.post(PATH, json=_body(study, username="Third", email="third@example.org"), headers=headers)

    text = caplog.text + json.dumps([r.args for r in caplog.records], default=str)
    for sentinel in (PASSWORD, USERNAME, USERNAME.lower(), EMAIL, EMAIL.lower(), stored_hash, pid,
                     "other_name", "other@example.org"):
        assert sentinel not in text, sentinel
    assert "frame_participants/create failed at users-insert: DuplicateKeyError" in caplog.text
    assert "frame_participants/create failed at sg-provision: SyncUserProvisioningError" in caplog.text


# --- wiring -------------------------------------------------------------------


def test_route_is_mounted_by_create_app_guarded_and_not_exempt():
    routes = [r for r in create_app().routes if isinstance(r, APIRoute) and r.path == PATH]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"POST"}
    assert not (route.openapi_extra or {}).get(ALLOW_UNAUTHENTICATED)
    assert any(d.call is require_write_principal for d in route.dependant.dependencies)
    assert any(
        d.call is require_write_principal for d in get_flat_dependant(route.dependant).dependencies
    )
    assert not any(r.path.startswith("/v1/api/participants") for r in create_app().routes if isinstance(r, APIRoute))


def test_unset_admin_url_warns_once_naming_only_the_keys_and_fails_only_at_use(caplog):
    caplog.set_level(logging.WARNING)
    deps = build_frame_participant_deps(db=object(), settings=SyncGatewaySettings(admin_url="", db=""))
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "SYNC_GATEWAY_ADMIN_URL" in warnings[0].getMessage()
    assert "SYNC_GATEWAY_DB" in warnings[0].getMessage()
    with pytest.raises(ValueError):
        deps.sync_users()


def test_set_admin_url_builds_the_sg_admin_repository_without_warning(caplog):
    caplog.set_level(logging.WARNING)
    deps = build_frame_participant_deps(
        db=object(), settings=SyncGatewaySettings(admin_url="http://sg-vm-secret-host:4985", db="spring")
    )
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
    repo = deps.sync_users()
    assert isinstance(repo, SGAdminUserRepository)
    assert deps.sync_users() is repo


def test_unset_admin_url_answers_500_at_use_time(app, client, root, participant_fakes):
    headers, study = root
    app.state.frame_participant_deps = build_frame_participant_deps(
        db=participant_fakes.db, settings=SyncGatewaySettings(admin_url="", db="")
    )
    resp = client.post(PATH, json=_body(study), headers=headers)
    _boom(resp, 500, "Internal Server Error", "An internal server error occurred")
    assert participant_fakes.raw["participants"].count_documents({}) == 0
