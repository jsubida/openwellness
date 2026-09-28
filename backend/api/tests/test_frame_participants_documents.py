"""Frame-shaped participant documents: Joi-equivalent validation, Mongoose
defaults, and a bcrypt hash node verifies (plan 10-07 Task 2)."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import bcrypt
import pytest
from bson import ObjectId

from openwellness_api.frame_participants.documents import (
    ParticipantValidationError,
    build_participant_doc,
    build_user_doc,
    hash_password,
    participant_response,
    validate_create_payload,
)

FIXTURE = Path(__file__).parent / "fixtures" / "frame_participant_joi_matrix.json"
MATRIX = json.loads(FIXTURE.read_text())["cases"]
# Raw request bodies whose numbers only JSON.parse can express (Infinity,
# a double-rounded integer), replayed through the hapi parser first.
BODY_MATRIX = json.loads(FIXTURE.read_text())["body_cases"]

# Joi's email() checks the TLD against IANA's list; email-validator does not.
# This is the ONLY case where ow and frame's Joi disagree, and it is recorded
# as an approximation in the plan summary.
KNOWN_DIVERGENCES = {"email_bogus_tld"}

STUDY = "0123456789abcdef01234567"
BASE = {
    "studyId": STUDY,
    "username": "Alice_1",
    "password": "pw",
    "email": "Alice@Example.com",
    "participantNumber": " P-001 ",
}
NOW = datetime(2026, 9, 28, 22, 1, 2, 345678, tzinfo=UTC)

# `new Participant(obj).toObject()` under frame's Mongoose 7.8.11, computed in
# the frame container (key names only), with _id moved first as mongod stores
# it and __v appended by save().
FRAME_PARTICIPANT_KEYS_MINIMAL = [
    "_id", "studyId", "couchId", "isActive", "isDropped", "googleId", "deviceId",
    "participantNumber", "user", "couchbaseUser", "condition", "settings", "study",
    "coach", "assessmentWeight", "startWeight", "participantType", "heightInInches",
    "participantStates", "age", "gender", "timeCreated", "__v",
]
FRAME_PARTICIPANT_KEYS_FULL = [
    "_id", "studyId", "couchId", "isActive", "isDropped", "assignedCoachId", "googleId",
    "deviceId", "participantNumber", "user", "couchbaseUser", "condition", "settings",
    "study", "coach", "assessmentWeight", "startWeight", "participantType",
    "heightInInches", "participantStates", "tz", "age", "gender", "timeCreated", "__v",
]
# frame's users Joi schema applied by mongo-models' constructor (Joi 17.13.4),
# plus the _id insertOne adds.
FRAME_USER_KEYS = [
    "_id", "email", "isActive", "password", "username", "location", "roles",
    "timeCreated", "verifiedId",
]


def payload(**overrides):
    body = dict(BASE)
    body.update(overrides)
    return body


# --- validate_create_payload -------------------------------------------------


@pytest.mark.parametrize("case", MATRIX, ids=[c["id"] for c in MATRIX])
def test_matches_frames_joi_verdict_and_converted_value(case):
    if case["id"] in KNOWN_DIVERGENCES:
        # Recorded approximation (Joi's IANA TLD allow-list): Joi refuses,
        # ow accepts. Asserted so that the divergence cannot silently widen.
        assert case["joi_ok"] is False
        validate_create_payload(case["payload"])
        return
    if case["joi_ok"]:
        assert validate_create_payload(case["payload"]) == case["joi_value"]
    else:
        with pytest.raises(ParticipantValidationError):
            validate_create_payload(case["payload"])


@pytest.mark.parametrize("case", BODY_MATRIX, ids=[c["id"] for c in BODY_MATRIX])
def test_raw_body_numbers_reach_joi_as_frame_parses_them(case):
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    parsed = parse_hapi_payload("application/json", case["body"].encode())
    assert parsed.response is None
    if case["joi_ok"]:
        out = validate_create_payload(parsed.payload)
        assert out == case["joi_value"]
        for key, value in case["joi_value"].items():
            assert type(out[key]) is type(value), key
    else:
        with pytest.raises(ParticipantValidationError) as exc:
            validate_create_payload(parsed.payload)
        assert str(exc.value).endswith(case["joi_error"])


def test_the_known_divergence_is_exactly_the_tld_allow_list():
    case = next(c for c in MATRIX if c["id"] == "email_bogus_tld")
    assert case["joi_ok"] is False
    assert validate_create_payload(case["payload"])["email"] == "a@example.invalidtld"


def test_valid_payload_is_normalized_with_joi_defaults():
    out = validate_create_payload(payload())
    assert out["username"] == "alice_1"
    assert out["email"] == "alice@example.com"
    assert out["location"] == ""
    assert out["participantType"] == 0
    assert out["heightInInches"] == 0
    assert out["participantStates"] == []
    assert out["participantNumber"] == " P-001 "  # trimmed by the handler, not Joi


def test_numeric_strings_convert():
    out = validate_create_payload(payload(participantType="2", heightInInches=" 70 ", age="40"))
    assert out["participantType"] == 2
    assert out["heightInInches"] == 70
    assert out["age"] == 40


@pytest.mark.parametrize("key", ["studyId", "username", "password", "email", "participantNumber"])
def test_missing_required_key_raises(key):
    body = payload()
    del body[key]
    with pytest.raises(ParticipantValidationError):
        validate_create_payload(body)


@pytest.mark.parametrize(
    "overrides",
    [
        {"studyId": STUDY[:23]},
        {"studyId": STUDY + "0"},
        {"id": STUDY[:23]},
        {"id": STUDY + "0"},
        {"username": "alice-1"},
        {"username": "alice.1"},
        {"email": "not-an-email"},
        {"gender": 2},
        {"participantStates": ["a", 1]},
        {"location": ""},
    ],
    ids=["studyId23", "studyId25", "id23", "id25", "username_dash", "username_dot",
         "email", "gender2", "states_non_string", "location_empty"],
)
def test_invalid_payload_raises(overrides):
    with pytest.raises(ParticipantValidationError):
        validate_create_payload(payload(**overrides))


def test_validation_error_text_never_carries_the_value():
    with pytest.raises(ParticipantValidationError) as info:
        validate_create_payload(payload(email="secret-sentinel-at-nowhere"))
    assert "secret-sentinel" not in str(info.value)


# --- build_participant_doc ---------------------------------------------------


def _participant(**overrides):
    body = validate_create_payload(payload(**overrides))
    pid = ObjectId()
    return pid, build_participant_doc(body, pid, ObjectId(STUDY), NOW)


def test_participant_doc_minimal_has_frames_key_set_in_frames_order():
    _, doc = _participant()
    assert list(doc) == FRAME_PARTICIPANT_KEYS_MINIMAL


def test_participant_doc_full_has_frames_key_set_in_frames_order():
    _, doc = _participant(
        assignedCoachId="0123456789abcdef01234568", tz="America/Chicago", startWeight=180,
        age=40, gender=1, location="Chicago", id="0123456789abcdef0123456a",
    )
    assert list(doc) == FRAME_PARTICIPANT_KEYS_FULL


def test_participant_doc_types_and_defaults():
    pid, doc = _participant(assignedCoachId="0123456789abcdef01234568")
    assert isinstance(doc["_id"], ObjectId) and doc["_id"] == pid
    assert isinstance(doc["studyId"], ObjectId) and doc["studyId"] == ObjectId(STUDY)
    assert isinstance(doc["assignedCoachId"], ObjectId)
    assert isinstance(doc["couchId"], str) and doc["couchId"] == str(pid)
    assert doc["participantNumber"] == "P-001"
    assert doc["__v"] == 0
    assert doc["isActive"] is True
    assert doc["isDropped"] is False
    for key in ("googleId", "deviceId", "user", "couchbaseUser", "condition", "settings",
                "study", "coach", "assessmentWeight", "startWeight", "age", "gender"):
        assert doc[key] is None, key
    assert doc["participantType"] == 0
    assert doc["heightInInches"] == 0
    assert doc["participantStates"] == []
    assert doc["timeCreated"] == datetime(2026, 9, 28, 22, 1, 2, 345000, tzinfo=UTC)


def test_participant_doc_carries_no_credential_or_undeclared_key():
    _, doc = _participant(location="Chicago", id="0123456789abcdef0123456a")
    for key in ("username", "password", "email", "location", "id", "userId"):
        assert key not in doc


def test_participant_doc_tz_only_when_supplied():
    _, without = _participant()
    _, null_tz = _participant(tz=None)
    assert "tz" not in without
    assert "tz" in null_tz and null_tz["tz"] is None


@pytest.mark.parametrize("overrides", [{"assignedCoachId": "coach"}, {"participantNumber": "   "}])
def test_values_frame_would_fail_on_after_writing_fail_before_any_write(overrides):
    body = validate_create_payload(payload(**overrides))  # Joi accepts both
    with pytest.raises(ValueError):
        build_participant_doc(body, ObjectId(), ObjectId(STUDY), NOW)


# --- build_user_doc / hash_password -----------------------------------------


def test_user_doc_has_frames_key_set_and_defaults():
    doc = build_user_doc(validate_create_payload(payload(location="Chicago")), NOW)
    assert list(doc) == FRAME_USER_KEYS
    assert isinstance(doc["_id"], ObjectId)
    assert doc["username"] == "alice_1"
    assert doc["email"] == "alice@example.com"
    assert doc["isActive"] is True
    assert doc["location"] == "Chicago"
    assert doc["roles"] == {}
    assert doc["verifiedId"] == ""
    assert doc["timeCreated"] == datetime(2026, 9, 28, 22, 1, 2, 345000, tzinfo=UTC)


def test_user_doc_password_is_a_verifiable_2b_10_hash_never_the_plaintext():
    doc = build_user_doc(validate_create_payload(payload(password="Plain-Sentinel")), NOW)
    assert doc["password"].startswith("$2b$10$")
    assert len(doc["password"]) == 60
    assert "Plain-Sentinel" not in json.dumps({k: str(v) for k, v in doc.items()})
    assert bcrypt.checkpw(b"Plain-Sentinel", doc["password"].encode())


def test_password_over_72_bytes_is_truncated_like_node_bcrypt():
    long_pw = "x" * 72 + "tail-ignored"
    hashed = hash_password(long_pw).encode()
    assert bcrypt.checkpw(b"x" * 72, hashed)


def test_multibyte_password_truncates_on_bytes_not_characters():
    pw = "é" * 40  # 80 UTF-8 bytes
    hashed = hash_password(pw).encode()
    assert bcrypt.checkpw(("é" * 36).encode("utf-8"), hashed)


# --- participant_response ----------------------------------------------------


def test_response_encodes_like_mongoose_to_json_and_attaches_user_with_hash():
    pid, pdoc = _participant(assignedCoachId="0123456789abcdef01234568")
    udoc = build_user_doc(validate_create_payload(payload()), NOW)
    pdoc["userId"] = udoc["_id"]
    udoc["roles"] = {"participant": {"pid": str(pid), "pnum": "P-001"}}
    body = participant_response(pdoc, udoc)
    assert body["_id"] == str(pid)
    assert body["studyId"] == STUDY
    assert body["userId"] == str(udoc["_id"])
    assert body["assignedCoachId"] == "0123456789abcdef01234568"
    assert body["timeCreated"] == "2026-09-28T22:01:02.345Z"
    assert body["user"]["_id"] == str(udoc["_id"])
    assert body["user"]["timeCreated"] == "2026-09-28T22:01:02.345Z"
    assert body["user"]["roles"] == {"participant": {"pid": str(pid), "pnum": "P-001"}}
    # D-11 parity (research Open Question 5 is flagged, not decided here).
    assert body["user"]["password"].startswith("$2b$10$")
    assert list(body)[: list(body).index("user")] == list(pdoc)[: list(pdoc).index("user")]
    json.dumps(body)


def test_response_accepts_naive_utc_datetimes_as_pymongo_returns_them():
    pid, pdoc = _participant()
    pdoc["timeCreated"] = datetime(2026, 1, 2, 3, 4, 5, 6000)
    body = participant_response(pdoc, build_user_doc(validate_create_payload(payload()), NOW))
    assert body["timeCreated"] == "2026-01-02T03:04:05.006Z"


# --- cross-runtime: node bcrypt.compare inside the frame container -----------

OPSERVER = Path("/Users/jc/Developer/Northwestern/opserver")
_COMPARE = "require('bcrypt').compare(process.argv[1], process.argv[2]).then(r=>console.log(r))"


def _node_compare(password: str, hashed: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "node", "-e", _COMPARE, password, hashed],
        cwd=OPSERVER, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-500:]
    return result.stdout.strip()


def _frame_container_available() -> str | None:
    if shutil.which("docker") is None:
        return "docker is not installed"
    if not OPSERVER.is_dir():
        return f"the opserver checkout is not at {OPSERVER}"
    probe = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "node", "-e", "require('bcrypt')"],
        cwd=OPSERVER, capture_output=True, text=True, timeout=60,
    )
    if probe.returncode != 0:
        return "the opserver dev stack's frame `api` container is not running (make dev)"
    return None


@pytest.mark.parametrize(
    ("password", "attempt", "expected"),
    [
        ("Phase10-sample", "Phase10-sample", "true"),
        ("Phase10-sample", "wrong", "false"),
        ("x" * 72 + "tail", "x" * 72 + "other-tail", "true"),
        ("été-☃", "été-☃", "true"),
    ],
    ids=["right", "wrong", "over_72_bytes", "multibyte"],
)
def test_node_bcrypt_in_the_frame_container_verifies_the_python_hash(password, attempt, expected):
    reason = _frame_container_available()
    if reason:
        pytest.skip(reason)
    assert _node_compare(attempt, hash_password(password)) == expected
