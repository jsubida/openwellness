"""Sync Gateway webhook parity: ``POST /api/eventHandlers/fitbitHeartRecord``.

HOOK-01. FastAPI answers the Sync Gateway ``document_changed`` webhook at the
path frame (hapi) serves today, and hands frame's exact Celery task name and
argument shape to a publisher port (D-01). The handler only reads: the
StudyComponentSetting reader, the Study reader on the 412 path, and the
publisher. It never writes (D-02).

Responses are byte-for-byte hapi parity (D-05). The expected status codes,
bodies, content-types and the eight security/CORS headers are the captured
frame responses in ``10-RESEARCH.md`` (Frame Contract Reference, "Captured
frame responses"), plus the ``server.inject`` results recorded there for
``return null`` (204, no content-type) and ``Boom.preconditionFailed`` (412).

The app here is built locally from ``build_event_handlers_router()`` with fake
ports on ``app.state``. Mounting into ``create_app()`` is a later plan.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from openwellness_api.deps.principal import ALLOW_UNAUTHENTICATED
from openwellness_api.event_handlers import build_event_handlers_router
from openwellness_api.event_handlers.hapi import UNDEFINED, js_string
from openwellness_api.event_handlers.legacy_studies import (
    LegacyStudyConfigError,
    LegacyStudyIds,
    LegacyStudyIdsProvider,
)
from openwellness_api.event_handlers.ports import (
    EventHandlerDeps,
    TaskPublishError,
)

PATH = "/api/eventHandlers/fitbitHeartRecord"
ACTIVITY_PATH = "/api/eventHandlers/activity"
POST_PATH = "/api/eventHandlers/post"
WEIGHT_PATH = "/api/eventHandlers/weight"
SMART_TASK = "jobs.smartRerandomization.waitForWeight"

# STUDY_SPECIFIC's three legacy ids (api/config.js:112-115), as test values.
SMART_ID = "5f0000000000000000000a01"
FTT_ID = "5f0000000000000000000a02"
MPOWER_ID = "5f0000000000000000000a03"
LEGACY_IDS = LegacyStudyIds(smart=SMART_ID, fit2thrive=FTT_ID, mpower=MPOWER_ID)
JSON_UTF8 = "application/json; charset=utf-8"
OWNER_SENTINEL = "owner-sentinel-7f3a9c"

# Verbatim from the captured frame responses (hapi `security: true, cors: true`).
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

BAD_REQUEST_MISSING = (
    b'{"statusCode":400,"error":"Bad Request","message":"Missing studyId"}'
)
BAD_REQUEST_JSON = (
    b'{"statusCode":400,"error":"Bad Request",'
    b'"message":"Invalid request payload JSON format"}'
)
INTERNAL = (
    b'{"statusCode":500,"error":"Internal Server Error",'
    b'"message":"An internal server error occurred"}'
)


def _precondition(message: str) -> bytes:
    return json.dumps(
        {"statusCode": 412, "error": "Precondition Failed", "message": message},
        separators=(",", ":"),
    ).encode()


# --------------------------------------------------------------------------- #
# Fakes (read ports + recording publisher). No write method exists on any.
# --------------------------------------------------------------------------- #


class FakeSettings:
    def __init__(self, rows: dict[tuple[Any, int], dict[str, Any]] | None = None):
        self.rows = rows or {}
        self.calls: list[tuple[Any, int]] = []

    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        self.calls.append((study_id, component_type))
        return self.rows.get((study_id, component_type))


class FakeStudies:
    def __init__(self, docs: dict[Any, dict[str, Any]] | None = None):
        self.docs = docs or {}
        self.calls: list[object] = []

    def find_by_id(self, study_id: object) -> dict[str, Any] | None:
        self.calls.append(study_id)
        return self.docs.get(study_id)


class RecordingPublisher:
    def __init__(self, raise_with: Exception | None = None):
        self.calls: list[tuple[str, list[Any]]] = []
        self.raise_with = raise_with

    def publish(self, task_name: str, args: list[Any]) -> None:
        if self.raise_with is not None:
            raise self.raise_with
        self.calls.append((task_name, args))


class FakeParticipants:
    def __init__(self) -> None:
        self.docs: dict[Any, dict[str, Any]] = {}
        self.calls: list[object] = []

    def find_by_couch_id(self, couch_id: object) -> dict[str, Any] | None:
        self.calls.append(couch_id)
        return self.docs.get(couch_id)


class FakeConditions:
    def __init__(self) -> None:
        self.latest_by_owner: dict[Any, dict[str, Any]] = {}
        self.calls: list[object] = []

    def latest(self, owner: object) -> dict[str, Any] | None:
        self.calls.append(owner)
        return self.latest_by_owner.get(owner)


class RaisingSettings:
    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        raise RuntimeError("view missing")


class Harness:
    def __init__(self) -> None:
        self.settings = FakeSettings()
        self.studies = FakeStudies()
        self.publisher = RecordingPublisher()
        self.participants = FakeParticipants()
        self.conditions = FakeConditions()
        self.legacy = LegacyStudyIdsProvider.of(LEGACY_IDS)
        self.app = FastAPI()
        self.app.include_router(build_event_handlers_router())
        self.install()
        self.client = TestClient(self.app)

    def install(
        self, settings: Any = None, legacy: LegacyStudyIdsProvider | None = None
    ) -> None:
        if legacy is not None:
            self.legacy = legacy
        self.app.state.event_handler_deps = EventHandlerDeps(
            settings=settings if settings is not None else self.settings,
            studies=self.studies,
            publisher=self.publisher,
            legacy_studies=self.legacy,
            conditions=self.conditions,
            participants=self.participants,
        )

    def post(self, body: bytes) -> Any:
        return self.post_to(PATH, body)

    def post_to(self, path: str, body: bytes) -> Any:
        return self.client.post(
            path, content=body, headers={"content-type": "application/json"}
        )


@pytest.fixture()
def h() -> Harness:
    return Harness()


def _assert_hapi_headers(resp: Any) -> None:
    for name, value in EXPECTED_HAPI_HEADERS.items():
        assert resp.headers.get(name) == value, name


def _assert_boom(resp: Any, status: int, body: bytes) -> None:
    assert resp.status_code == status
    assert resp.content == body
    assert resp.headers["content-type"] == JSON_UTF8
    _assert_hapi_headers(resp)


def _observer_setting(value: Any = UNDEFINED, study_id: str = "s1") -> dict[str, Any]:
    setting: dict[str, Any] = {"studyId": study_id, "componentType": 2}
    if value is not UNDEFINED:
        setting["fitbitHeartObserver"] = value
    return setting


# --------------------------------------------------------------------------- #
# 400 / 500 before any lookup
# --------------------------------------------------------------------------- #


def test_empty_object_is_400_missing_study_id(h: Harness) -> None:
    resp = h.post(b"{}")
    _assert_boom(resp, 400, BAD_REQUEST_MISSING)
    assert h.publisher.calls == []
    assert h.settings.calls == []


def test_malformed_json_is_400_invalid_payload(h: Harness) -> None:
    _assert_boom(h.post(b"{bad"), 400, BAD_REQUEST_JSON)
    assert h.publisher.calls == []


def test_nan_is_rejected_as_invalid_json(h: Harness) -> None:
    _assert_boom(h.post(b'{"studyId": NaN}'), 400, BAD_REQUEST_JSON)
    assert h.settings.calls == []


def test_non_object_json_is_400_missing_study_id(h: Harness) -> None:
    _assert_boom(h.post(b"[]"), 400, BAD_REQUEST_MISSING)


@pytest.mark.parametrize("body", [b"", b"null"], ids=["empty", "json-null"])
def test_null_payload_is_hapi_500(h: Harness, body: bytes) -> None:
    _assert_boom(h.post(body), 500, INTERNAL)
    assert h.publisher.calls == []


# --------------------------------------------------------------------------- #
# 412 preconditions
# --------------------------------------------------------------------------- #


def test_no_component_setting_is_412(h: Harness) -> None:
    resp = h.post(b'{"studyId":"s1"}')
    _assert_boom(
        resp, 412, _precondition("Study (s1): no component settings of type 2")
    )
    assert h.settings.calls == [("s1", 2)]
    assert h.studies.calls == []


def test_null_study_id_passes_require_study_id_and_renders_as_null(
    h: Harness,
) -> None:
    resp = h.post(b'{"studyId":null}')
    _assert_boom(
        resp, 412, _precondition("Study (null): no component settings of type 2")
    )
    assert h.settings.calls == [(None, 2)]


def test_missing_observer_key_is_412_with_study_name(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting()
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    resp = h.post(b'{"studyId":"s1","owner":"o1"}')
    _assert_boom(
        resp, 412, _precondition("Study (Pilot) has no fitbitHeartObserver value")
    )
    assert h.studies.calls == ["s1"]
    assert h.publisher.calls == []


def test_empty_observer_value_is_412(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting("")
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    resp = h.post(b'{"studyId":"s1","owner":"o1"}')
    _assert_boom(
        resp, 412, _precondition("Study (Pilot) has no fitbitHeartObserver value")
    )
    assert h.publisher.calls == []


def test_study_without_name_renders_undefined(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting()
    h.studies.docs["s1"] = {"_id": "s1"}
    resp = h.post(b'{"studyId":"s1"}')
    _assert_boom(
        resp,
        412,
        _precondition("Study (undefined) has no fitbitHeartObserver value"),
    )


def test_null_observer_value_is_500_before_any_study_lookup(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting(None)
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    _assert_boom(h.post(b'{"studyId":"s1","owner":"o1"}'), 500, INTERNAL)
    assert h.studies.calls == []
    assert h.publisher.calls == []


def test_missing_study_doc_on_412_path_is_500(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting()
    _assert_boom(h.post(b'{"studyId":"s1","owner":"o1"}'), 500, INTERNAL)
    assert h.studies.calls == ["s1"]
    assert h.publisher.calls == []


# --------------------------------------------------------------------------- #
# Success and publish
# --------------------------------------------------------------------------- #


def test_success_publishes_frames_task_and_answers_204(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting("jobs.a.b")
    resp = h.post(b'{"studyId":"s1","owner":"o1"}')
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    assert "content-length" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == [("jobs.a.b", ["o1"])]
    # D-02: one settings read, no study read on the success path.
    assert h.settings.calls == [("s1", 2)]
    assert h.studies.calls == []


def test_missing_owner_publishes_null_arg(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting("jobs.a.b")
    resp = h.post(b'{"studyId":"s1"}')
    assert resp.status_code == 204
    assert h.publisher.calls == [("jobs.a.b", [None])]
    assert json.dumps(h.publisher.calls[0][1]) == "[null]"


def test_non_string_observer_publishes_nothing_logs_and_answers_204(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting(5)
    body = json.dumps({"studyId": "s1", "owner": OWNER_SENTINEL}).encode()
    with caplog.at_level(logging.DEBUG):
        resp = h.post(body)
    assert resp.status_code == 204
    assert "content-type" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "eventHandlers/fitbitHeartRecord" in errors[0].getMessage()
    assert OWNER_SENTINEL not in caplog.text


def test_publish_failure_is_500_and_logs_only_route_and_class(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    h.settings.rows[("s1", 2)] = _observer_setting("jobs.a.b")
    h.publisher.raise_with = TaskPublishError(f"broker down for {OWNER_SENTINEL}")
    body = json.dumps({"studyId": "s1", "owner": OWNER_SENTINEL}).encode()
    with caplog.at_level(logging.DEBUG):
        resp = h.post(body)
    _assert_boom(resp, 500, INTERNAL)
    assert "eventHandlers/fitbitHeartRecord failed: TaskPublishError" in caplog.text
    assert OWNER_SENTINEL not in caplog.text
    assert "jobs.a.b" not in caplog.text


def test_reader_failure_is_hapi_500_not_starlette_plain_text(h: Harness) -> None:
    h.install(settings=RaisingSettings())
    _assert_boom(h.post(b'{"studyId":"s1"}'), 500, INTERNAL)


def test_missing_deps_on_app_state_is_hapi_500() -> None:
    app = FastAPI()
    app.include_router(build_event_handlers_router())
    resp = TestClient(app).post(
        PATH, content=b'{"studyId":"s1"}', headers={"content-type": "application/json"}
    )
    _assert_boom(resp, 500, INTERNAL)


# --------------------------------------------------------------------------- #
# POST /api/eventHandlers/post (Social, postObserver, [owner, _id])
# --------------------------------------------------------------------------- #


def _setting(
    component_type: int, name: str, value: Any = UNDEFINED, study_id: Any = "s1"
) -> dict[str, Any]:
    setting: dict[str, Any] = {"studyId": study_id, "componentType": component_type}
    if value is not UNDEFINED:
        setting[name] = value
    return setting


def test_post_empty_object_is_400_missing_study_id(h: Harness) -> None:
    _assert_boom(h.post_to(POST_PATH, b"{}"), 400, BAD_REQUEST_MISSING)
    assert h.settings.calls == []
    assert h.publisher.calls == []


def test_post_without_social_setting_is_412_type_4(h: Harness) -> None:
    resp = h.post_to(POST_PATH, b'{"studyId":"s1"}')
    _assert_boom(
        resp, 412, _precondition("Study (s1): no component settings of type 4")
    )
    assert h.settings.calls == [("s1", 4)]


def test_post_missing_post_observer_is_412_with_study_name(h: Harness) -> None:
    h.settings.rows[("s1", 4)] = _setting(4, "postObserver")
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    resp = h.post_to(POST_PATH, b'{"studyId":"s1","owner":"o","_id":"d"}')
    _assert_boom(resp, 412, _precondition("Study (Pilot) has no postObserver value"))
    assert h.publisher.calls == []


def test_post_publishes_owner_and_doc_id_and_answers_204(h: Harness) -> None:
    h.settings.rows[("s1", 4)] = _setting(4, "postObserver", "jobs.p")
    resp = h.post_to(POST_PATH, b'{"studyId":"s1","owner":"o","_id":"d"}')
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == [("jobs.p", ["o", "d"])]
    assert h.studies.calls == []


def test_post_missing_owner_and_id_publish_nulls(h: Harness) -> None:
    h.settings.rows[("s1", 4)] = _setting(4, "postObserver", "jobs.p")
    resp = h.post_to(POST_PATH, b'{"studyId":"s1"}')
    assert resp.status_code == 204
    assert h.publisher.calls == [("jobs.p", [None, None])]
    assert json.dumps(h.publisher.calls[0][1]) == "[null, null]"


def test_post_ignores_the_legacy_list(h: Harness) -> None:
    """Frame's ``post`` handler has no legacy branch."""
    h.settings.rows[(SMART_ID, 4)] = _setting(4, "postObserver", "jobs.p", SMART_ID)
    body = json.dumps({"studyId": SMART_ID, "owner": "o", "_id": "d"}).encode()
    assert h.post_to(POST_PATH, body).status_code == 204
    assert h.publisher.calls == [("jobs.p", ["o", "d"])]


# --------------------------------------------------------------------------- #
# POST /api/eventHandlers/activity (Activity, activityObserver, [owner])
# --------------------------------------------------------------------------- #


def test_activity_without_activity_setting_is_412_type_2(h: Harness) -> None:
    resp = h.post_to(ACTIVITY_PATH, b'{"studyId":"s1"}')
    _assert_boom(
        resp, 412, _precondition("Study (s1): no component settings of type 2")
    )


def test_activity_missing_observer_is_412_with_study_name(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _setting(2, "activityObserver")
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    resp = h.post_to(ACTIVITY_PATH, b'{"studyId":"s1","owner":"o"}')
    _assert_boom(
        resp, 412, _precondition("Study (Pilot) has no activityObserver value")
    )


def test_activity_non_legacy_publishes_owner_and_answers_204(h: Harness) -> None:
    h.settings.rows[("s1", 2)] = _setting(2, "activityObserver", "jobs.a")
    resp = h.post_to(ACTIVITY_PATH, b'{"studyId":"s1","owner":"o","_id":"x"}')
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == [("jobs.a", ["o"])]


@pytest.mark.parametrize("study_id", [SMART_ID, FTT_ID, MPOWER_ID])
def test_activity_legacy_study_answers_204_without_enqueueing(
    h: Harness, study_id: str
) -> None:
    h.settings.rows[(study_id, 2)] = _setting(2, "activityObserver", "jobs.a", study_id)
    body = json.dumps({"studyId": study_id, "owner": "o", "_id": "x"}).encode()
    resp = h.post_to(ACTIVITY_PATH, body)
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == []
    # The pre chain ran exactly as for any study: one settings read, no study.
    assert h.settings.calls == [(study_id, 2)]
    assert h.studies.calls == []
    # D-03: none of processLegacyActivity's participant or Condition reads.
    assert h.participants.calls == []
    assert h.conditions.calls == []


@pytest.mark.parametrize("study_id", [SMART_ID, FTT_ID, MPOWER_ID])
def test_activity_legacy_study_still_runs_the_pre_chain(
    h: Harness, study_id: str
) -> None:
    body = json.dumps({"studyId": study_id, "owner": "o"}).encode()
    resp = h.post_to(ACTIVITY_PATH, body)
    _assert_boom(
        resp,
        412,
        _precondition(f"Study ({study_id}): no component settings of type 2"),
    )
    h.settings.rows[(study_id, 2)] = _setting(2, "activityObserver", "", study_id)
    h.studies.docs[study_id] = {"_id": study_id, "name": "Legacy"}
    _assert_boom(
        h.post_to(ACTIVITY_PATH, body),
        412,
        _precondition("Study (Legacy) has no activityObserver value"),
    )
    assert h.publisher.calls == []


def test_activity_legacy_match_is_strict_equality(h: Harness) -> None:
    """``includes`` is SameValueZero: a number never equals a string id."""
    h.install(
        legacy=LegacyStudyIdsProvider.of(LegacyStudyIds(smart="12345"))
    )
    h.settings.rows[(12345, 2)] = _setting(2, "activityObserver", "jobs.a", 12345)
    resp = h.post_to(ACTIVITY_PATH, b'{"studyId":12345,"owner":"o"}')
    assert resp.status_code == 204
    assert h.publisher.calls == [("jobs.a", ["o"])]


@pytest.mark.parametrize(
    "raw", [None, "", "not json", "[1, 2]", "null", '"smart"'],
    ids=["unset", "empty", "not-json", "array", "null", "string"],
)
def test_activity_with_unusable_study_specific_is_500_never_non_legacy(
    h: Harness, caplog: pytest.LogCaptureFixture, raw: str | None
) -> None:
    h.install(legacy=LegacyStudyIdsProvider.from_value(raw))
    h.settings.rows[("s1", 2)] = _setting(2, "activityObserver", "jobs.a")
    with caplog.at_level(logging.DEBUG):
        resp = h.post_to(ACTIVITY_PATH, b'{"studyId":"s1","owner":"o"}')
    _assert_boom(resp, 500, INTERNAL)
    assert h.publisher.calls == []
    assert "eventHandlers/activity failed: LegacyStudyConfigError" in caplog.text


def test_activity_unusable_study_specific_does_not_mask_earlier_answers(
    h: Harness,
) -> None:
    """Frame answers its pre chain first; only the handler needs the list."""
    h.install(legacy=LegacyStudyIdsProvider.from_value(None))
    _assert_boom(h.post_to(ACTIVITY_PATH, b"{}"), 400, BAD_REQUEST_MISSING)
    _assert_boom(
        h.post_to(ACTIVITY_PATH, b'{"studyId":"s1"}'),
        412,
        _precondition("Study (s1): no component settings of type 2"),
    )


def test_activity_study_specific_without_the_other_keys_is_non_legacy(
    h: Harness,
) -> None:
    h.install(legacy=LegacyStudyIdsProvider.from_value('{"smartId":"x"}'))
    h.settings.rows[("s1", 2)] = _setting(2, "activityObserver", "jobs.a")
    resp = h.post_to(ACTIVITY_PATH, b'{"studyId":"s1","owner":"o"}')
    assert resp.status_code == 204
    assert h.publisher.calls == [("jobs.a", ["o"])]


def test_activity_null_study_id_never_matches_a_missing_legacy_key(
    h: Harness,
) -> None:
    """A missing key is ``undefined`` in frame; ``null`` is not ``undefined``."""
    h.install(legacy=LegacyStudyIdsProvider.from_value('{"smartId":"x"}'))
    h.settings.rows[(None, 2)] = _setting(2, "activityObserver", "jobs.a", None)
    resp = h.post_to(ACTIVITY_PATH, b'{"studyId":null,"owner":"o"}')
    assert resp.status_code == 204
    assert h.publisher.calls == [("jobs.a", ["o"])]


def test_activity_reads_study_specific_from_the_process_env(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "STUDY_SPECIFIC",
        json.dumps({"smartId": SMART_ID, "fit2ThriveId": FTT_ID, "mPowerId": MPOWER_ID}),
    )
    h.install(legacy=LegacyStudyIdsProvider.from_process_env())
    h.settings.rows[(FTT_ID, 2)] = _setting(2, "activityObserver", "jobs.a", FTT_ID)
    h.settings.rows[("s1", 2)] = _setting(2, "activityObserver", "jobs.a")
    legacy = json.dumps({"studyId": FTT_ID, "owner": "o"}).encode()
    assert h.post_to(ACTIVITY_PATH, legacy).status_code == 204
    assert h.publisher.calls == []
    assert h.post_to(ACTIVITY_PATH, b'{"studyId":"s1","owner":"o"}').status_code == 204
    assert h.publisher.calls == [("jobs.a", ["o"])]


# --------------------------------------------------------------------------- #
# POST /api/eventHandlers/weight (Weight, inline weightObserver, [owner, _id])
# --------------------------------------------------------------------------- #


def _weight_body(study_id: str = "s1", owner: str = "o", doc_id: str = "w") -> bytes:
    return json.dumps({"studyId": study_id, "owner": owner, "_id": doc_id}).encode()


def _assert_no_legacy_reads(h: Harness) -> None:
    assert h.participants.calls == []
    assert h.conditions.calls == []


def test_weight_empty_object_is_400_missing_study_id(h: Harness) -> None:
    _assert_boom(h.post_to(WEIGHT_PATH, b"{}"), 400, BAD_REQUEST_MISSING)
    assert h.settings.calls == []


def test_weight_non_legacy_publishes_owner_and_id_and_answers_204(
    h: Harness,
) -> None:
    h.settings.rows[("s1", 1)] = _setting(1, "weightObserver", "jobs.w")
    resp = h.post_to(WEIGHT_PATH, _weight_body())
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == [("jobs.w", ["o", "w"])]
    assert h.settings.calls == [("s1", 1)]
    assert h.studies.calls == []
    _assert_no_legacy_reads(h)


def test_weight_missing_owner_and_id_publish_nulls(h: Harness) -> None:
    h.settings.rows[("s1", 1)] = _setting(1, "weightObserver", "jobs.w")
    assert h.post_to(WEIGHT_PATH, b'{"studyId":"s1"}').status_code == 204
    assert h.publisher.calls == [("jobs.w", [None, None])]


def test_weight_without_weight_setting_is_412_type_1(h: Harness) -> None:
    resp = h.post_to(WEIGHT_PATH, _weight_body())
    _assert_boom(
        resp, 412, _precondition("Study (s1): no component settings of type 1")
    )
    assert h.settings.calls == [("s1", 1)]


@pytest.mark.parametrize("value", [UNDEFINED, "", []], ids=["missing", "empty", "empty-array"])
def test_weight_missing_observer_looks_up_the_payloads_study(
    h: Harness, value: Any
) -> None:
    # The setting names another study: frame's inline pre ignores it and
    # looks up ``request.payload.studyId``.
    h.settings.rows[("s1", 1)] = _setting(1, "weightObserver", value, "setting-study")
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    h.studies.docs["setting-study"] = {"_id": "setting-study", "name": "Wrong"}
    resp = h.post_to(WEIGHT_PATH, _weight_body())
    _assert_boom(resp, 412, _precondition("Study (Pilot) has no weightObserver value"))
    assert h.studies.calls == ["s1"]
    assert h.publisher.calls == []


def test_weight_missing_observer_for_an_unknown_study_is_500(h: Harness) -> None:
    h.settings.rows[("s1", 1)] = _setting(1, "weightObserver")
    _assert_boom(h.post_to(WEIGHT_PATH, _weight_body()), 500, INTERNAL)
    assert h.studies.calls == ["s1"]


def test_weight_null_observer_is_500_before_any_study_lookup(h: Harness) -> None:
    h.settings.rows[("s1", 1)] = _setting(1, "weightObserver", None)
    h.studies.docs["s1"] = {"_id": "s1", "name": "Pilot"}
    _assert_boom(h.post_to(WEIGHT_PATH, _weight_body()), 500, INTERNAL)
    assert h.studies.calls == []
    assert h.publisher.calls == []


def _smart(
    h: Harness,
    *,
    participant: dict[str, Any] | None = None,
    condition: dict[str, Any] | None = None,
    owner: str = "o",
) -> None:
    h.settings.rows[(SMART_ID, 1)] = _setting(1, "weightObserver", "jobs.w", SMART_ID)
    if participant is not None:
        h.participants.docs[owner] = participant
    if condition is not None:
        h.conditions.latest_by_owner[owner] = condition


def test_smart_weight_pending_publishes_wait_for_weight(h: Harness) -> None:
    pid = ObjectId()
    _smart(
        h,
        participant={"_id": pid, "couchId": "o", "isActive": True, "participantType": 0},
        condition={"responderState": 0},
    )
    resp = h.post_to(WEIGHT_PATH, _weight_body(SMART_ID))
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    _assert_hapi_headers(resp)
    assert h.publisher.calls == [(SMART_TASK, [str(pid), "w"])]
    assert h.publisher.calls[0][1][0] == format(pid)
    assert len(h.publisher.calls[0][1][0]) == 24
    assert h.participants.calls == ["o"]
    assert h.conditions.calls == ["o"]


def test_smart_weight_default_fields_behave_as_mongoose_defaults(h: Harness) -> None:
    """No ``isActive`` / ``participantType``: Mongoose's defaults (true, 0) apply."""
    pid = ObjectId()
    _smart(h, participant={"_id": pid, "couchId": "o"}, condition={"responderState": 0})
    assert h.post_to(WEIGHT_PATH, _weight_body(SMART_ID)).status_code == 204
    assert h.publisher.calls == [(SMART_TASK, [str(pid), "w"])]


@pytest.mark.parametrize(
    "state", [1, 2, 3, "0", False, None, UNDEFINED],
    ids=["nonresponder", "responder", "mia", "string-0", "false", "null", "missing"],
)
def test_smart_weight_non_pending_publishes_nothing(h: Harness, state: Any) -> None:
    condition: dict[str, Any] = {} if state is UNDEFINED else {"responderState": state}
    _smart(
        h,
        participant={"_id": ObjectId(), "isActive": True, "participantType": 0},
        condition=condition,
    )
    resp = h.post_to(WEIGHT_PATH, _weight_body(SMART_ID))
    assert resp.status_code == 204
    assert "content-type" not in resp.headers
    assert h.publisher.calls == []
    assert h.conditions.calls == ["o"]


def test_smart_weight_pending_float_zero_publishes(h: Harness) -> None:
    """``0.0 === 0`` in JS: a JSON ``0.0`` is still PENDING."""
    pid = ObjectId()
    _smart(h, participant={"_id": pid}, condition={"responderState": 0.0})
    assert h.post_to(WEIGHT_PATH, _weight_body(SMART_ID)).status_code == 204
    assert h.publisher.calls == [(SMART_TASK, [str(pid), "w"])]


@pytest.mark.parametrize(
    "participant",
    [
        {"isActive": False, "participantType": 0},
        {"isActive": True, "participantType": 3},
        {"isActive": False, "participantType": 3},
    ],
    ids=["inactive", "ftt-buddy", "inactive-buddy"],
)
def test_smart_weight_inactive_or_buddy_answers_204_before_the_condition_read(
    h: Harness, participant: dict[str, Any]
) -> None:
    _smart(
        h,
        participant={"_id": ObjectId(), **participant},
        condition={"responderState": 0},
    )
    resp = h.post_to(WEIGHT_PATH, _weight_body(SMART_ID))
    assert resp.status_code == 204
    assert h.publisher.calls == []
    assert h.participants.calls == ["o"]
    assert h.conditions.calls == []


def test_smart_weight_without_condition_answers_204(h: Harness) -> None:
    _smart(h, participant={"_id": ObjectId(), "isActive": True, "participantType": 0})
    resp = h.post_to(WEIGHT_PATH, _weight_body(SMART_ID))
    assert resp.status_code == 204
    assert resp.content == b""
    assert h.publisher.calls == []
    assert h.conditions.calls == ["o"]


def test_smart_weight_unknown_participant_is_500(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    """``Object.keys(null)`` throws in frame before its not-found log."""
    _smart(h, condition={"responderState": 0})
    body = _weight_body(SMART_ID, owner=OWNER_SENTINEL)
    with caplog.at_level(logging.DEBUG):
        resp = h.post_to(WEIGHT_PATH, body)
    _assert_boom(resp, 500, INTERNAL)
    assert h.publisher.calls == []
    assert h.participants.calls == [OWNER_SENTINEL]
    assert h.conditions.calls == []
    assert "eventHandlers/weight failed: TypeError" in caplog.text
    assert OWNER_SENTINEL not in caplog.text


def test_smart_weight_publish_failure_is_500(h: Harness) -> None:
    _smart(h, participant={"_id": ObjectId()}, condition={"responderState": 0})
    h.publisher.raise_with = TaskPublishError("broker down")
    _assert_boom(h.post_to(WEIGHT_PATH, _weight_body(SMART_ID)), 500, INTERNAL)


def test_smart_weight_still_runs_the_pre_chain(h: Harness) -> None:
    resp = h.post_to(WEIGHT_PATH, _weight_body(SMART_ID))
    _assert_boom(
        resp,
        412,
        _precondition(f"Study ({SMART_ID}): no component settings of type 1"),
    )
    _assert_no_legacy_reads(h)


def test_smart_weight_never_publishes_the_settings_observer(h: Harness) -> None:
    pid = ObjectId()
    _smart(h, participant={"_id": pid}, condition={"responderState": 0})
    h.post_to(WEIGHT_PATH, _weight_body(SMART_ID))
    assert [name for name, _ in h.publisher.calls] == [SMART_TASK]


@pytest.mark.parametrize("study_id", [FTT_ID, MPOWER_ID])
def test_fit2thrive_and_mpower_weight_answer_204_with_no_reads(
    h: Harness, study_id: str
) -> None:
    h.settings.rows[(study_id, 1)] = _setting(1, "weightObserver", "jobs.w", study_id)
    h.participants.docs["o"] = {"_id": ObjectId(), "isActive": True}
    h.conditions.latest_by_owner["o"] = {"responderState": 0}
    resp = h.post_to(WEIGHT_PATH, _weight_body(study_id))
    assert resp.status_code == 204
    assert resp.content == b""
    assert "content-type" not in resp.headers
    assert h.publisher.calls == []
    _assert_no_legacy_reads(h)


def test_weight_with_unusable_study_specific_is_500(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    h.install(legacy=LegacyStudyIdsProvider.from_value("not json"))
    h.settings.rows[("s1", 1)] = _setting(1, "weightObserver", "jobs.w")
    with caplog.at_level(logging.DEBUG):
        resp = h.post_to(WEIGHT_PATH, _weight_body())
    _assert_boom(resp, 500, INTERNAL)
    assert h.publisher.calls == []
    assert "eventHandlers/weight failed: LegacyStudyConfigError" in caplog.text


def test_smart_weight_unwired_readers_are_500_not_a_silent_skip(
    h: Harness,
) -> None:
    h.app.state.event_handler_deps = EventHandlerDeps(
        settings=h.settings,
        studies=h.studies,
        publisher=h.publisher,
        legacy_studies=h.legacy,
    )
    h.settings.rows[(SMART_ID, 1)] = _setting(1, "weightObserver", "jobs.w", SMART_ID)
    _assert_boom(h.post_to(WEIGHT_PATH, _weight_body(SMART_ID)), 500, INTERNAL)
    assert h.publisher.calls == []


# --------------------------------------------------------------------------- #
# legacy_studies: STUDY_SPECIFIC parsing
# --------------------------------------------------------------------------- #


def test_legacy_ids_parse_frames_three_keys() -> None:
    raw = json.dumps(
        {
            "smartId": SMART_ID,
            "fit2ThriveId": FTT_ID,
            "mPowerId": MPOWER_ID,
            "ftmbId": "ignored",
        }
    )
    assert LegacyStudyIdsProvider.from_value(raw).get() == LEGACY_IDS


def test_legacy_ids_contains_only_non_null_string_ids() -> None:
    ids = LegacyStudyIds(smart="a")
    assert ids.contains("a") is True
    assert ids.contains("b") is False
    assert ids.contains(None) is False
    assert ids.is_smart("a") is True
    assert LEGACY_IDS.is_smart(FTT_ID) is False


def test_explicit_null_key_is_treated_as_absent() -> None:
    ids = LegacyStudyIdsProvider.from_value('{"smartId":null,"mPowerId":"m"}').get()
    assert ids == LegacyStudyIds(mpower="m")
    assert ids.contains(None) is False


@pytest.mark.parametrize(
    "raw", [None, "", "   ", "not json", "[]", "null", "5", '{"smartId": 5}'],
)
def test_unusable_study_specific_raises_without_echoing_the_value(
    raw: str | None,
) -> None:
    provider = LegacyStudyIdsProvider.from_value(raw)
    with pytest.raises(LegacyStudyConfigError) as info:
        provider.get()
    assert "STUDY_SPECIFIC" in str(info.value)
    if raw and raw.strip():
        assert raw not in str(info.value)
    # Still failing on the next request: never cached as non-legacy.
    with pytest.raises(LegacyStudyConfigError):
        provider.get()


def test_from_process_env_parses_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUDY_SPECIFIC", '{"smartId":"first"}')
    provider = LegacyStudyIdsProvider.from_process_env()
    assert provider.get() == LegacyStudyIds(smart="first")
    monkeypatch.setenv("STUDY_SPECIFIC", '{"smartId":"second"}')
    assert provider.get() == LegacyStudyIds(smart="first")


def test_from_process_env_does_not_read_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STUDY_SPECIFIC", raising=False)
    provider = LegacyStudyIdsProvider.from_process_env()
    monkeypatch.setenv("STUDY_SPECIFIC", '{"mPowerId":"m"}')
    assert provider.get() == LegacyStudyIds(mpower="m")


def test_event_handler_deps_default_to_the_process_env_provider() -> None:
    deps = EventHandlerDeps(
        settings=FakeSettings(), studies=FakeStudies(), publisher=RecordingPublisher()
    )
    assert isinstance(deps.legacy_studies, LegacyStudyIdsProvider)


# --------------------------------------------------------------------------- #
# Route shape
# --------------------------------------------------------------------------- #


SG_PATHS = [PATH, ACTIVITY_PATH, POST_PATH, WEIGHT_PATH]


@pytest.mark.parametrize("path", SG_PATHS)
def test_every_sg_route_is_literal_post_only_and_unauthenticated(path: str) -> None:
    routes = [
        r
        for r in build_event_handlers_router().routes
        if isinstance(r, APIRoute) and r.path == path
    ]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"POST"}
    assert (route.openapi_extra or {}).get(ALLOW_UNAUTHENTICATED) is True
    assert route.dependant.dependencies == []
    assert route.body_field is None


def test_every_sg_route_is_registered_before_the_catch_all() -> None:
    paths = [
        r.path for r in build_event_handlers_router().routes if isinstance(r, APIRoute)
    ]
    catch_all = paths.index("/api/eventHandlers{rest:path}")
    assert catch_all == len(paths) - 1
    for path in SG_PATHS:
        assert paths.index(path) < catch_all


def test_route_is_literal_post_only_and_marked_unauthenticated() -> None:
    routes = [
        r
        for r in build_event_handlers_router().routes
        if isinstance(r, APIRoute) and r.path == PATH
    ]
    assert len(routes) == 1
    route = routes[0]
    assert route.methods == {"POST"}
    assert (route.openapi_extra or {}).get(ALLOW_UNAUTHENTICATED) is True
    assert route.dependant.dependencies == []
    assert route.body_field is None


# --------------------------------------------------------------------------- #
# js_string (JS String() semantics used in frame's 412 messages)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "null"),
        (UNDEFINED, "undefined"),
        (True, "true"),
        (False, "false"),
        (0, "0"),
        (-12, "-12"),
        (2.0, "2"),
        (1.5, "1.5"),
        (-0.0, "0"),
        (0.1, "0.1"),
        (1e21, "1e+21"),
        (1.5e-7, "1.5e-7"),
        (0.000001, "0.000001"),
        (123456789012345680000.0, "123456789012345680000"),
        (float("inf"), "Infinity"),
        (float("-inf"), "-Infinity"),
        (float("nan"), "NaN"),
        ("s1", "s1"),
        ("", ""),
        ([], ""),
        ([1, None, "a"], "1,,a"),
        ([1, [2, 3]], "1,2,3"),
        ({}, "[object Object]"),
        ({"a": 1}, "[object Object]"),
    ],
)
def test_js_string_matches_javascript(value: Any, expected: str) -> None:
    assert js_string(value) == expected
