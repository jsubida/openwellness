"""hapi payload interpretation, replayed from frame's own recorded answers.

HOOK-01, D-05. Every entry in ``fixtures/frame_payload_matrix.json`` was
captured live from frame (hapi 21.4.10, ``api`` submodule ``6706a1e5``) by
POSTing the entry's content-type and body straight to
``http://api:3000/api/eventHandlers/fitbitHeartRecord`` from inside the dev
``edge`` container. Only nginx-origin headers (``server``, ``date``,
``connection``) were dropped.

Dev frame has no ``studyComponentSetting`` design doc, so any payload that
reaches ``requireComponentSetting`` answers 500 there. The settings reader
here raises for the same reason, which makes "reached the settings lookup"
observable as the same 500 on both sides.

A fixture body is ``base64decode(body_b64) * body_repeat``: the bodies over
1 MiB are one repeated byte, stored compactly.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openwellness_api.event_handlers import build_event_handlers_router
from openwellness_api.event_handlers.ports import EventHandlerDeps

PATH = "/api/eventHandlers/fitbitHeartRecord"
FIXTURE = Path(__file__).parent / "fixtures" / "frame_payload_matrix.json"
MATRIX: list[dict[str, Any]] = json.loads(FIXTURE.read_text())


class RaisingSettings:
    """Stands in for dev's missing design doc: frame answers 500 there."""

    def __init__(self) -> None:
        self.calls = 0

    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        self.calls += 1
        raise RuntimeError("design doc missing")


class NoStudies:
    def find_by_id(self, study_id: object) -> dict[str, Any] | None:
        raise AssertionError("the study reader must not be reached")


class NoPublisher:
    def publish(self, task_name: str, args: list[Any]) -> None:
        raise AssertionError("nothing may be published")


@pytest.fixture()
def harness() -> tuple[TestClient, RaisingSettings]:
    settings = RaisingSettings()
    app = FastAPI()
    app.include_router(build_event_handlers_router())
    app.state.event_handler_deps = EventHandlerDeps(
        settings=settings, studies=NoStudies(), publisher=NoPublisher()
    )
    return TestClient(app), settings


def _body(entry: dict[str, Any]) -> bytes:
    return base64.b64decode(entry["body_b64"]) * entry.get("body_repeat", 1)


def _post(client: TestClient, entry: dict[str, Any]) -> Any:
    headers = {}
    if entry["content_type"] is not None:
        headers["content-type"] = entry["content_type"]
    return client.post(PATH, content=_body(entry), headers=headers)


def _entry(case_id: str) -> dict[str, Any]:
    return next(e for e in MATRIX if e["id"] == case_id)


def test_fixture_holds_the_captured_matrix() -> None:
    required = {
        "id",
        "content_type",
        "body_b64",
        "frame_status",
        "frame_content_type",
        "frame_body",
    }
    assert len(MATRIX) >= 18
    assert all(required <= set(entry) for entry in MATRIX)
    assert len({entry["id"] for entry in MATRIX}) == len(MATRIX)


@pytest.mark.parametrize("entry", MATRIX, ids=[e["id"] for e in MATRIX])
def test_replays_frames_captured_answer(
    harness: tuple[TestClient, RaisingSettings], entry: dict[str, Any]
) -> None:
    client, _ = harness
    resp = _post(client, entry)

    assert resp.status_code == entry["frame_status"]
    assert resp.content == entry["frame_body"].encode("utf-8")
    assert resp.headers.get("content-type") == entry["frame_content_type"]
    for name, value in entry["frame_headers"].items():
        assert resp.headers.get(name) == value, name


def test_body_over_one_mebibyte_is_413_without_a_settings_read(
    harness: tuple[TestClient, RaisingSettings],
) -> None:
    client, settings = harness
    entry = _entry("json_over_1mib")
    assert len(_body(entry)) == 1048577

    resp = _post(client, entry)

    assert resp.status_code == 413
    assert resp.content == entry["frame_body"].encode("utf-8")
    assert settings.calls == 0


def test_body_of_exactly_one_mebibyte_is_parsed(
    harness: tuple[TestClient, RaisingSettings],
) -> None:
    client, _ = harness
    entry = _entry("json_exactly_1mib")
    assert len(_body(entry)) == 1048576

    resp = _post(client, entry)

    assert resp.status_code == 400  # whitespace-only JSON, not 413


@pytest.mark.parametrize("case_id", ["xml_unsupported", "multipart"])
def test_unsupported_content_type_is_415(
    harness: tuple[TestClient, RaisingSettings], case_id: str
) -> None:
    client, settings = harness
    entry = _entry(case_id)

    resp = _post(client, entry)

    assert resp.status_code == 415
    assert resp.content == entry["frame_body"].encode("utf-8")
    assert settings.calls == 0


# --------------------------------------------------------------------------- #
# parse_hapi_payload directly: the parsed value frame's handler would see
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("content_type", "raw", "expected"),
    [
        (None, b'{"studyId":"s"}', {"studyId": "s"}),
        ("", b"[1]", [1]),
        ("application/json", b"", None),
        ("application/vnd.test+json", b"true", True),
        ("APPLICATION/JSON; charset=latin1", b"1.5", 1.5),
        ("text/plain", b"", ""),
        ("text/html", b"\xff", "�"),
        ("application/octet-stream", b"", None),
        ("application/octet-stream", b"ab", b"ab"),
        ("application/x-www-form-urlencoded", b"", {}),
        (
            "application/x-www-form-urlencoded",
            b"a=1&a=2&b=x+y%21&c&a[b]=3",
            {"a": ["1", "2"], "b": "x y!", "c": "", "a[b]": "3"},
        ),
    ],
)
def test_parse_hapi_payload_values(
    content_type: str | None, raw: bytes, expected: Any
) -> None:
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    result = parse_hapi_payload(content_type, raw)

    assert result.response is None
    assert result.payload == expected
    assert type(result.payload) is type(expected)


def test_form_parse_stops_at_node_max_keys() -> None:
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    raw = "&".join(f"k{i}=v" for i in range(1001)).encode()

    result = parse_hapi_payload("application/x-www-form-urlencoded", raw)

    assert result.response is None
    assert len(result.payload) == 1000
    assert "k1000" not in result.payload


def test_json_nested_past_pythons_recursion_limit_still_parses() -> None:
    """V8's JSON.parse is not recursive: frame parsed 100 000 levels live."""
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    depth = 100_000
    raw = b'{"studyId":"s","x":' + b"[" * depth + b"]" * depth + b"}"

    result = parse_hapi_payload("application/json", raw)

    assert result.response is None
    assert result.payload["studyId"] == "s"
    node, seen = result.payload["x"], 1
    while node:
        node, seen = node[0], seen + 1
    assert seen == depth


@pytest.mark.parametrize(
    "raw",
    [
        b"[" * 5000 + b"]" * 4999,
        b"[" * 5000 + b"NaN" + b"]" * 5000,
        b'{"a":' * 5000 + b'{"__proto__":1}' + b"}" * 5000,
        b"[" * 5000 + b"1,]" + b"]" * 4999,
    ],
    ids=["unbalanced", "nan", "proto-key", "trailing-comma"],
)
def test_deep_invalid_json_is_400(raw: bytes) -> None:
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    result = parse_hapi_payload("application/json", raw)

    assert result.response is not None
    assert result.response.status_code == 400
    assert json.loads(bytes(result.response.body))["message"] == (
        "Invalid request payload JSON format"
    )


# --------------------------------------------------------------------------- #
# Numbers are doubles, as JSON.parse makes them
# --------------------------------------------------------------------------- #

# ``JSON.stringify({a: JSON.parse(literal)})`` captured with ``node -e`` in
# frame's api container. node-celery publishes task arguments with
# JSON.stringify, so these are the exact bytes frame puts on the broker.
V8_NUMBER_ROUND_TRIPS = [
    ("9007199254740993", '{"a":9007199254740992}'),
    ("9007199254740992", '{"a":9007199254740992}'),
    ("123", '{"a":123}'),
    ("1.0", '{"a":1}'),
    ("-0", '{"a":0}'),
    ("1e21", '{"a":1e+21}'),
    ("100000000000000000000", '{"a":100000000000000000000}'),
    ("123456789012345678901234", '{"a":1.2345678901234569e+23}'),
    ("1.5e300", '{"a":1.5e+300}'),
]


@pytest.mark.parametrize(("literal", "v8"), V8_NUMBER_ROUND_TRIPS)
def test_json_numbers_round_trip_like_v8(literal: str, v8: str) -> None:
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    result = parse_hapi_payload("application/json", b'{"a":' + literal.encode() + b"}")

    assert result.response is None
    assert json.dumps(result.payload, separators=(",", ":")) == v8


@pytest.mark.parametrize(("literal", "v8"), V8_NUMBER_ROUND_TRIPS)
def test_deep_json_numbers_round_trip_like_v8(literal: str, v8: str) -> None:
    """The iterative fallback parser applies the same number rule."""
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    depth = 5000
    raw = b'{"a":' + b"[" * depth + literal.encode() + b"]" * depth + b"}"

    result = parse_hapi_payload("application/json", raw)

    assert result.response is None
    node = result.payload["a"]
    for _ in range(depth):
        node = node[0]
    assert json.dumps({"a": node}, separators=(",", ":")) == v8


@pytest.mark.parametrize("deep", [False, True])
def test_integral_numbers_stay_int_and_overflow_is_infinity(deep: bool) -> None:
    from openwellness_api.event_handlers.hapi import parse_hapi_payload

    items = b"[123,1.0,-0,9007199254740993,0.5,1e21," + b"1" + b"0" * 400 + b"]"
    raw = b"[" * 5000 + items + b"]" * 5000 if deep else items

    result = parse_hapi_payload("application/json", raw)

    assert result.response is None
    values = result.payload
    while deep and isinstance(values[0], list):
        values = values[0]
    assert [type(v) for v in values] == [int, int, int, int, float, float, float]
    assert values[:4] == [123, 1, 0, 9007199254740992]
    assert values[6] == float("inf")  # JSON.parse gives Infinity


def test_published_owner_is_rounded_like_frame(client: TestClient, event_fakes: Any) -> None:
    event_fakes.settings.rows[("s1", 2)] = {
        "studyId": "s1",
        "fitbitHeartObserver": "jobs.fitbit.heart",
    }

    resp = client.post(
        PATH,
        content=b'{"studyId":"s1","owner":9007199254740993}',
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 204
    assert event_fakes.publisher.calls == [("jobs.fitbit.heart", [9007199254740992])]
    (_, args), = event_fakes.publisher.calls
    assert json.dumps(args) == "[9007199254740992]"
