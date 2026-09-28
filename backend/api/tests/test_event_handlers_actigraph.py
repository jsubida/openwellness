"""ActiGraph webhook parity: ``POST /api/eventHandlers/actigraph``.

HOOK-02, D-01, D-05 (as corrected by research) and D-17. ow answers the
vendor-registered path frame (hapi) serves today
(``api/server/api/event-handlers.js:312-412``):

- A truthy ``ValidationCode`` is the subscription handshake: 200,
  ``Validation Code Received``, ``text/html``, the code echoed in
  ``x-actigraph-hook-secret``. No credential is presented or required.
- Otherwise the notification pre chain runs: incomplete, no device, or no
  participant is ``h.close`` (a bare 200); a missing Activity (2) setting or
  ``actigraphObserver`` is 412; success publishes
  ``[participant.couchId, EventNotification]`` under the observer value and
  answers ``return ''`` (204 ``text/html``), not 200.

Every response in ``fixtures/frame_actigraph_matrix.json`` was captured live
from frame (see ``test_event_handlers_actigraph_notification.py``) and is
replayed here byte for byte, with the device lookup finding nothing as it
did on dev for the ``__parity_none_`` subject.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import mongomock
import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from openwellness_api.deps.principal import ALLOW_UNAUTHENTICATED
from openwellness_api.event_handlers import build_event_handlers_router
from openwellness_api.event_handlers.mongo_readers import (
    MongoDeviceReader,
    MongoParticipantReader,
)
from openwellness_api.event_handlers.ports import EventHandlerDeps, TaskPublishError

PATH = "/api/eventHandlers/actigraph"
FIXTURE = Path(__file__).parent / "fixtures" / "frame_actigraph_matrix.json"
MATRIX: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))

OBSERVER = "jobs.prove.actigraphObserver.handleNotification"
HTML_UTF8 = "text/html; charset=utf-8"
JSON_UTF8 = "application/json; charset=utf-8"
HOOK_HEADER = "x-actigraph-hook-secret"
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
INTERNAL = (
    b'{"statusCode":500,"error":"Internal Server Error",'
    b'"message":"An internal server error occurred"}'
)
NO_OBSERVER = (
    b'{"statusCode":412,"error":"Precondition Failed",'
    b'"message":"No value for actigraphObserver"}'
)

# Frame's documented "Processing Completed" notification.
COMPLETED = {
    "status": "completed",
    "firstEpochUTC": "2020-02-22T23:01:00.0000000",
    "firstEpochSubjectTZ": "2020-02-22T17:01:00.0000000",
    "lastEpochUTC": "2020-02-23T22:57:00.0000000",
    "lastEpochSubjectTZ": "2020-02-23T16:57:00.0000000",
    "uploadId": "683530",
    "studyId": "579",
    "subjectId": "28953",
}
# What frame publishes for COMPLETED under TZ=America/Chicago.
COMPLETED_NOTIF = {
    "status": "completed",
    "uploadId": "683530",
    "studyId": "579",
    "subjectId": "28953",
    "start": "2020-02-23T05:01:00.000Z",
    "end": "2020-02-24T04:57:00.000Z",
}


# --------------------------------------------------------------------------- #
# Fakes: the real Mongo readers over mongomock, recorded; fake settings.
# --------------------------------------------------------------------------- #


class RecordingDevices(MongoDeviceReader):
    def __init__(self, db: Any) -> None:
        super().__init__(db)
        self.calls: list[object] = []

    def first_by_serial_number(self, serial_number: str) -> dict[str, Any] | None:
        self.calls.append(serial_number)
        return super().first_by_serial_number(serial_number)


class RecordingParticipants(MongoParticipantReader):
    def __init__(self, db: Any) -> None:
        super().__init__(db)
        self.by_id_calls: list[object] = []

    def find_by_id(self, participant_id: object) -> dict[str, Any] | None:
        self.by_id_calls.append(participant_id)
        return super().find_by_id(participant_id)


class FakeSettings:
    def __init__(self) -> None:
        self.rows: dict[tuple[Any, int], dict[str, Any]] = {}
        self.calls: list[tuple[Any, int]] = []

    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        self.calls.append((study_id, component_type))
        return self.rows.get((study_id, component_type))


class NoStudies:
    def find_by_id(self, study_id: object) -> dict[str, Any] | None:
        raise AssertionError("the ActiGraph route never reads a study")


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any]]] = []
        self.raise_with: Exception | None = None
        self._lock = threading.Lock()

    def publish(self, task_name: str, args: list[Any]) -> None:
        if self.raise_with is not None:
            raise self.raise_with
        with self._lock:
            self.calls.append((task_name, args))


class Harness:
    def __init__(self) -> None:
        self.db = mongomock.MongoClient().db
        self.devices = RecordingDevices(self.db)
        self.participants = RecordingParticipants(self.db)
        self.settings = FakeSettings()
        self.publisher = RecordingPublisher()
        self.app = FastAPI()
        self.app.include_router(build_event_handlers_router())
        self.app.state.event_handler_deps = EventHandlerDeps(
            settings=self.settings,
            studies=NoStudies(),
            publisher=self.publisher,
            participants=self.participants,
            devices=self.devices,
        )
        self.client = TestClient(self.app)

    def seed(
        self,
        *,
        serial: str = "28953",
        study_id: Any = None,
        couch_id: Any = "couch-C1",
        observer: Any = OBSERVER,
        with_setting: bool = True,
    ) -> ObjectId:
        """A device -> participant -> Activity setting chain; returns the study id."""
        study = study_id if study_id is not None else ObjectId()
        pid = ObjectId()
        self.db["devices"].insert_one(
            {"_id": ObjectId(), "serialNumber": serial, "participantId": pid}
        )
        participant: dict[str, Any] = {"_id": pid, "studyId": study}
        if couch_id is not None:
            participant["couchId"] = couch_id
        self.db["participants"].insert_one(participant)
        if with_setting:
            key = str(study) if isinstance(study, ObjectId) else study
            setting: dict[str, Any] = {"componentType": 2}
            if observer is not _ABSENT:
                setting["actigraphObserver"] = observer
            self.settings.rows[(key, 2)] = setting
        return study

    def post(self, payload: Any, content_type: str = "application/json") -> Any:
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return self.client.post(PATH, content=body, headers={"content-type": content_type})


_ABSENT = object()


@pytest.fixture()
def h(monkeypatch: pytest.MonkeyPatch) -> Harness:
    monkeypatch.setenv("TZ", "America/Chicago")
    return Harness()


def _headers(resp: Any) -> dict[str, str]:
    """Raw response headers as the fixture stores them (latin-1, lines joined)."""
    out: dict[str, str] = {}
    for name, value in resp.headers.raw:
        key = name.decode("latin-1").lower()
        text = value.decode("latin-1")
        out[key] = out[key] + "\n" + text if key in out else text
    return out


def _assert_closed(resp: Any) -> None:
    """``h.close``: a bare 200 with ``content-length: 0`` and nothing else."""
    assert resp.status_code == 200
    assert resp.content == b""
    assert _headers(resp) == {"content-length": "0"}


def _assert_precondition(resp: Any, message: str) -> None:
    assert resp.status_code == 412
    assert resp.headers["content-type"] == JSON_UTF8
    assert resp.content == json.dumps(
        {"statusCode": 412, "error": "Precondition Failed", "message": message},
        separators=(",", ":"),
    ).encode()


def _assert_internal(resp: Any) -> None:
    assert resp.status_code == 500
    assert resp.content == INTERNAL
    assert resp.headers["content-type"] == JSON_UTF8


# --------------------------------------------------------------------------- #
# Captured frame responses, replayed byte for byte
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entry", MATRIX["responses"], ids=lambda e: e["id"])
def test_captured_frame_response_replays(h: Harness, entry: dict[str, Any]) -> None:
    body = base64.b64decode(entry["body_b64"])
    resp = h.post(body, entry["content_type"])

    assert resp.status_code == entry["frame_status"]
    assert resp.content.decode("utf-8") == entry["frame_body"]
    assert _headers(resp) == entry["frame_headers"]
    assert h.publisher.calls == []


# --------------------------------------------------------------------------- #
# Handshake
# --------------------------------------------------------------------------- #


def test_handshake_answers_200_echo_and_hapi_headers(h: Harness) -> None:
    resp = h.post({"ValidationCode": "abc123"})

    assert resp.status_code == 200
    assert resp.content == b"Validation Code Received"
    assert resp.headers["content-type"] == HTML_UTF8
    assert resp.headers["content-length"] == "24"
    assert resp.headers[HOOK_HEADER] == "abc123"
    for name, value in EXPECTED_HAPI_HEADERS.items():
        assert resp.headers[name] == value, name


def test_handshake_wins_over_a_completed_notification(h: Harness) -> None:
    h.seed()
    resp = h.post({**COMPLETED, "ValidationCode": "v1"})

    assert resp.status_code == 200
    assert resp.headers[HOOK_HEADER] == "v1"
    assert h.devices.calls == []
    assert h.publisher.calls == []


def test_handshake_needs_no_credential(h: Harness) -> None:
    resp = h.client.post(
        PATH,
        content=b'{"ValidationCode":"x"}',
        headers={"content-type": "application/json", "X-Principal-Id": "forged"},
    )
    assert resp.status_code == 200
    assert resp.headers[HOOK_HEADER] == "x"


# --------------------------------------------------------------------------- #
# Notification pre chain
# --------------------------------------------------------------------------- #


def test_completed_notification_publishes_couch_id_and_notif_and_answers_204(
    h: Harness,
) -> None:
    h.seed()
    resp = h.post(COMPLETED)

    assert resp.status_code == 204
    assert resp.content == b""
    assert resp.headers["content-type"] == HTML_UTF8
    for name, value in EXPECTED_HAPI_HEADERS.items():
        assert resp.headers[name] == value, name
    assert h.publisher.calls == [(OBSERVER, ["couch-C1", COMPLETED_NOTIF])]
    task, args = h.publisher.calls[0]
    assert list(args[1]) == ["status", "uploadId", "studyId", "subjectId", "start", "end"]
    assert h.devices.calls == ["28953"]


def test_setting_is_looked_up_by_the_participants_study_hex(h: Harness) -> None:
    study = h.seed()
    h.post(COMPLETED)
    assert h.settings.calls == [(str(study), 2)]


def test_string_study_id_is_used_as_is(h: Harness) -> None:
    h.seed(study_id="5f00000000000000000000aa")
    resp = h.post(COMPLETED)
    assert resp.status_code == 204
    assert h.settings.calls == [("5f00000000000000000000aa", 2)]


def test_start_and_end_follow_the_process_tz(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.seed()
    monkeypatch.setenv("TZ", "UTC")
    h.post(COMPLETED)
    notif = h.publisher.calls[0][1][1]
    assert notif["start"] == "2020-02-22T23:01:00.000Z"
    assert notif["end"] == "2020-02-23T22:57:00.000Z"


def test_missing_couch_id_publishes_null(h: Harness) -> None:
    h.seed(couch_id=None)
    resp = h.post(COMPLETED)
    assert resp.status_code == 204
    assert h.publisher.calls == [(OBSERVER, [None, COMPLETED_NOTIF])]


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "started", "subjectId": "28953"},
        {"status": "Completed", "subjectId": "28953"},
        {"status": ["completed"], "subjectId": "28953"},
        {"subjectId": "28953"},
        [],
        "completed",
    ],
    ids=["started", "case", "array", "absent", "array-body", "string-body"],
)
def test_incomplete_notification_is_a_bare_200(h: Harness, payload: Any) -> None:
    h.seed()
    _assert_closed(h.post(payload))
    assert h.devices.calls == []
    assert h.publisher.calls == []


def test_unknown_device_is_a_bare_200(h: Harness) -> None:
    h.seed(serial="11111")
    _assert_closed(h.post(COMPLETED))
    assert h.devices.calls == ["28953"]
    assert h.participants.by_id_calls == []


def test_absent_subject_id_is_a_bare_200_without_a_device_query(h: Harness) -> None:
    # Deliberate deviation from frame: Mongoose drops an undefined filter
    # value, so frame's Device.find({serialNumber: undefined}) matches every
    # device and enqueues a job for whichever participant owns the first one.
    h.seed()
    payload = {k: v for k, v in COMPLETED.items() if k != "subjectId"}
    _assert_closed(h.post(payload))
    assert h.devices.calls == []
    assert h.publisher.calls == []


@pytest.mark.parametrize("subject", [None, {"$gt": ""}, ["28953"], {}])
def test_null_or_non_scalar_subject_id_is_a_bare_200_without_a_query(
    h: Harness, subject: Any
) -> None:
    h.seed()
    _assert_closed(h.post({**COMPLETED, "subjectId": subject}))
    assert h.devices.calls == []
    assert h.publisher.calls == []


def test_numeric_subject_id_is_cast_to_string_as_mongoose_does(h: Harness) -> None:
    h.seed()
    resp = h.post({**COMPLETED, "subjectId": 28953})
    assert resp.status_code == 204
    assert h.devices.calls == ["28953"]
    # The notification keeps the payload's own value.
    assert h.publisher.calls[0][1][1]["subjectId"] == 28953


def test_device_without_participant_id_is_a_bare_200(h: Harness) -> None:
    h.db["devices"].insert_one({"_id": ObjectId(), "serialNumber": "28953"})
    _assert_closed(h.post(COMPLETED))
    assert h.participants.by_id_calls == [None]


def test_device_with_null_participant_id_is_a_bare_200(h: Harness) -> None:
    h.db["devices"].insert_one(
        {"_id": ObjectId(), "serialNumber": "28953", "participantId": None}
    )
    _assert_closed(h.post(COMPLETED))


def test_unknown_participant_is_a_bare_200(h: Harness) -> None:
    h.db["devices"].insert_one(
        {"_id": ObjectId(), "serialNumber": "28953", "participantId": ObjectId()}
    )
    _assert_closed(h.post(COMPLETED))
    assert h.settings.calls == []


def test_malformed_participant_id_is_500(h: Harness) -> None:
    h.db["devices"].insert_one(
        {"_id": ObjectId(), "serialNumber": "28953", "participantId": "not-an-id"}
    )
    _assert_internal(h.post(COMPLETED))


def test_missing_activity_setting_is_412_naming_the_study_hex(h: Harness) -> None:
    study = h.seed(with_setting=False)
    _assert_precondition(
        h.post(COMPLETED), f"Study ({study}): no component settings of type 2"
    )
    assert h.publisher.calls == []


@pytest.mark.parametrize(
    "observer",
    [_ABSENT, "", [], {"length": 0}],
    ids=["absent", "empty", "empty-array", "length-0"],
)
def test_missing_or_empty_observer_is_412(h: Harness, observer: Any) -> None:
    h.seed(observer=observer)
    resp = h.post(COMPLETED)
    assert resp.status_code == 412
    assert resp.content == NO_OBSERVER
    assert h.publisher.calls == []


def test_null_observer_is_500(h: Harness) -> None:
    h.seed(observer=None)
    _assert_internal(h.post(COMPLETED))
    assert h.publisher.calls == []


@pytest.mark.parametrize("observer", [5, True, {"a": 1}, ["jobs.x"]])
def test_non_string_observer_publishes_nothing_logs_once_and_answers_204(
    h: Harness, observer: Any, caplog: pytest.LogCaptureFixture
) -> None:
    h.seed(observer=observer)
    with caplog.at_level(logging.INFO):
        resp = h.post(COMPLETED)
    assert resp.status_code == 204
    assert resp.headers["content-type"] == HTML_UTF8
    assert h.publisher.calls == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "actigraph" in errors[0].getMessage()


def test_publish_failure_is_500(h: Harness, caplog: pytest.LogCaptureFixture) -> None:
    h.seed()
    h.publisher.raise_with = TaskPublishError("broker down")
    with caplog.at_level(logging.INFO):
        _assert_internal(h.post(COMPLETED))
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["eventHandlers/actigraph failed: TaskPublishError"]


def test_null_payload_is_500(h: Harness) -> None:
    _assert_internal(h.post(b"null"))
    _assert_internal(h.post(b""))


def test_invalid_tz_is_500_not_a_shifted_window(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    h.seed()
    monkeypatch.setenv("TZ", "Not/AZone")
    _assert_internal(h.post(COMPLETED))
    assert h.publisher.calls == []


# --------------------------------------------------------------------------- #
# HOOK-02 concurrency: no shared state, no dedupe
# --------------------------------------------------------------------------- #


def test_concurrent_handshakes_each_echo_their_own_code(h: Harness) -> None:
    barrier = threading.Barrier(2)

    def handshake(code: str) -> str:
        client = TestClient(h.app)
        barrier.wait()
        resp = client.post(PATH, json={"ValidationCode": code})
        assert resp.status_code == 200
        return resp.headers[HOOK_HEADER]

    for _ in range(10):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(handshake, "A")
            b = pool.submit(handshake, "B")
            assert (a.result(), b.result()) == ("A", "B")
        barrier.reset()


def test_two_identical_completed_notifications_publish_twice(h: Harness) -> None:
    h.seed()
    barrier = threading.Barrier(2)

    def notify() -> int:
        client = TestClient(h.app)
        barrier.wait()
        return client.post(PATH, json=COMPLETED).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(notify), pool.submit(notify)]
        statuses = [future.result() for future in futures]
    assert statuses == [204, 204]
    assert h.publisher.calls == [
        (OBSERVER, ["couch-C1", COMPLETED_NOTIF]),
        (OBSERVER, ["couch-C1", COMPLETED_NOTIF]),
    ]


# --------------------------------------------------------------------------- #
# Logging (T-10-29): the code, the notification and ids never reach a log
# --------------------------------------------------------------------------- #


def test_validation_codes_never_appear_in_logs(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    codes = ["sentinel-code-4c1d", "sentinel\r\ncrlf-9e2a", "sentinel-✓-77b0", ["sentinel-arr-51f3"]]
    with caplog.at_level(logging.DEBUG):
        for code in codes:
            h.post({"ValidationCode": code})
    assert "sentinel" not in caplog.text
    failures = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert failures == ["eventHandlers/actigraph failed: InvalidHeaderValue"] * 2


def test_notification_values_never_appear_in_logs(
    h: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    h.seed(serial="serial-sentinel-3f", couch_id="couch-sentinel-8a")
    h.db["devices"].insert_one(
        {"_id": ObjectId(), "serialNumber": "bad-sentinel", "participantId": "not-an-id"}
    )
    with caplog.at_level(logging.DEBUG):
        h.post({**COMPLETED, "subjectId": "serial-sentinel-3f", "uploadId": "upload-sentinel"})
        h.post({**COMPLETED, "subjectId": "bad-sentinel"})
        h.post({**COMPLETED, "subjectId": "unknown-sentinel"})
    assert "sentinel" not in caplog.text


# --------------------------------------------------------------------------- #
# Registration and exemption
# --------------------------------------------------------------------------- #


def test_route_is_literal_post_only_unauthenticated_and_unguarded() -> None:
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


def test_route_is_registered_before_the_catch_all() -> None:
    paths = [
        r.path for r in build_event_handlers_router().routes if isinstance(r, APIRoute)
    ]
    catch_all = paths.index("/api/eventHandlers{rest:path}")
    assert catch_all == len(paths) - 1
    assert paths.index(PATH) < catch_all


@pytest.mark.parametrize("path", [PATH + "/", PATH + "x", PATH + "/extra"])
def test_adjacent_uris_are_hapi_404(h: Harness, path: str) -> None:
    resp = h.client.post(path, json={"ValidationCode": "x"})
    assert resp.status_code == 404
    assert HOOK_HEADER not in resp.headers


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_wrong_method_is_hapi_404(h: Harness, method: str) -> None:
    resp = h.client.request(method, PATH)
    assert resp.status_code == 404
