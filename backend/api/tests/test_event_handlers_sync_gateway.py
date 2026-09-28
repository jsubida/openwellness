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
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from openwellness_api.deps.principal import ALLOW_UNAUTHENTICATED
from openwellness_api.event_handlers import build_event_handlers_router
from openwellness_api.event_handlers.hapi import UNDEFINED, js_string
from openwellness_api.event_handlers.ports import (
    EventHandlerDeps,
    TaskPublishError,
)

PATH = "/api/eventHandlers/fitbitHeartRecord"
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


class RaisingSettings:
    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        raise RuntimeError("view missing")


class Harness:
    def __init__(self) -> None:
        self.settings = FakeSettings()
        self.studies = FakeStudies()
        self.publisher = RecordingPublisher()
        self.app = FastAPI()
        self.app.include_router(build_event_handlers_router())
        self.install()
        self.client = TestClient(self.app)

    def install(self, settings: Any = None) -> None:
        self.app.state.event_handler_deps = EventHandlerDeps(
            settings=settings if settings is not None else self.settings,
            studies=self.studies,
            publisher=self.publisher,
        )

    def post(self, body: bytes) -> Any:
        return self.client.post(
            PATH, content=body, headers={"content-type": "application/json"}
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
# Route shape
# --------------------------------------------------------------------------- #


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
