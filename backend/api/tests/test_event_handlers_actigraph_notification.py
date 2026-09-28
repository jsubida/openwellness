"""ActiGraph value semantics, replayed from frame's and V8's recorded answers.

HOOK-02, D-17. ``fixtures/frame_actigraph_matrix.json`` was captured live on
the opserver dev stack (frame = ``api`` submodule ``6706a1e5``, hapi 21.4.10,
node v22.23.1):

- ``responses``: each body POSTed straight to
  ``http://api:3000/api/eventHandlers/actigraph`` from inside the ``edge``
  container. Header values are the raw wire bytes decoded as latin-1, with
  only the single space after ``name:`` removed; repeated header lines are
  joined with ``\\n``. nginx-origin headers are dropped.
- ``dates``: ``JSON.stringify(new Date(input))`` printed by ``node -e`` in
  the ``api`` container, whose ``TZ`` is recorded under ``tz``.

The consumer (``jobs/classes/actigraph/eventNotification.py``) does
``arrow.get(data['start'])``, so a wrong ``start``/``end`` makes the worker
fetch the wrong data window and nothing errors (T-10-31).
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from openwellness_api.event_handlers.actigraph_notification import (
    InvalidHeaderValue,
    js_date_json,
    js_truthy,
    local_tz_from_env,
    serialize_event_notification,
    validation_header_value,
)
from openwellness_api.event_handlers.hapi import UNDEFINED

FIXTURE = Path(__file__).parent / "fixtures" / "frame_actigraph_matrix.json"
MATRIX: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
TZ = ZoneInfo(MATRIX["tz"])
HEADER = "x-actigraph-hook-secret"

# Captured V8 outputs this implementation does not reproduce. Every entry
# here must also be listed in the plan summary as a recorded divergence.
DATE_DIVERGENCES: frozenset[str] = frozenset()


def _payload(entry: dict[str, Any]) -> Any:
    return json.loads(base64.b64decode(entry["body_b64"]) or b"null")


def _handshake_cases() -> list[dict[str, Any]]:
    """Captured JSON bodies whose ``ValidationCode`` frame treated as truthy."""
    cases = []
    for entry in MATRIX["responses"]:
        if entry["content_type"] != "application/json":
            continue
        payload = _payload(entry)
        if not isinstance(payload, dict) or "ValidationCode" not in payload:
            continue
        if entry["frame_body"] == "":  # h.close: the code was falsy
            continue
        cases.append(entry)
    return cases


def _falsy_code_cases() -> list[dict[str, Any]]:
    cases = []
    for entry in MATRIX["responses"]:
        payload = _payload(entry)
        if isinstance(payload, dict) and "ValidationCode" in payload and entry["frame_body"] == "":
            cases.append(entry)
    return cases


# --------------------------------------------------------------------------- #
# The fixture itself
# --------------------------------------------------------------------------- #


def test_fixture_holds_the_captures_the_plan_requires() -> None:
    assert MATRIX["tz"] == "America/Chicago"
    assert len(MATRIX["responses"]) >= 15
    assert len(MATRIX["dates"]) >= 15
    ids = {entry["id"] for entry in MATRIX["dates"]}
    for required in (
        "actigraph_7digit",
        "actigraph_7digit_fraction",
        "utc_z",
        "offset_plus2",
        "date_only",
        "dst_ambiguous",
        "dst_gap",
        "space_separated",
        "slash_form",
        "not_a_date",
        "empty_string",
        "epoch_ms",
        "fractional_number",
        "json_null",
        "bool_true",
        "undefined",
    ):
        assert required in ids


# --------------------------------------------------------------------------- #
# js_truthy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value", [{}, [], "x", " ", "0", "false", 1, -1, 0.5, True, {"a": 1}, ["a"], b"x"]
)
def test_js_truthy_true(value: object) -> None:
    assert js_truthy(value) is True


@pytest.mark.parametrize(
    "value", [None, False, 0, 0.0, -0.0, "", math.nan, UNDEFINED]
)
def test_js_truthy_false(value: object) -> None:
    assert js_truthy(value) is False


def test_js_truthy_agrees_with_every_captured_validation_code() -> None:
    for entry in _handshake_cases():
        assert js_truthy(_payload(entry)["ValidationCode"]) is True, entry["id"]
    for entry in _falsy_code_cases():
        assert js_truthy(_payload(entry)["ValidationCode"]) is False, entry["id"]


# --------------------------------------------------------------------------- #
# The echoed header value
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entry", _handshake_cases(), ids=lambda e: e["id"])
def test_validation_header_value_matches_frame(entry: dict[str, Any]) -> None:
    code = _payload(entry)["ValidationCode"]
    if entry["frame_status"] == 500:
        with pytest.raises(InvalidHeaderValue):
            validation_header_value(code)
        return
    assert entry["frame_status"] == 200
    captured = entry["frame_headers"].get(HEADER)
    expected = () if captured is None else tuple(captured.split("\n"))
    assert validation_header_value(code) == expected


def test_crlf_and_control_characters_are_never_echoed() -> None:
    # T-10-28: response splitting. Node's header-value check rejects them.
    for code in ("a\r\nb", "a\nb", "a\rb", "a\u0007b", "a\u0000b", "a\u007fb", ["x", "a\r\nb"]):
        with pytest.raises(InvalidHeaderValue):
            validation_header_value(code)


def test_non_latin1_is_rejected_and_latin1_goes_out_as_utf8_bytes() -> None:
    with pytest.raises(InvalidHeaderValue):
        validation_header_value("✓")
    # Frame writes the header block with the string body, as UTF-8.
    (value,) = validation_header_value("é")
    assert value.encode("latin-1") == "é".encode("utf-8")


def test_invalid_header_value_message_never_carries_the_code() -> None:
    with pytest.raises(InvalidHeaderValue) as info:
        validation_header_value("secret\r\nvalue")
    assert "secret" not in str(info.value)


# --------------------------------------------------------------------------- #
# V8 Date semantics
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entry", MATRIX["dates"], ids=lambda e: e["id"])
def test_js_date_json_replays_v8(entry: dict[str, Any]) -> None:
    if entry["id"] in DATE_DIVERGENCES:
        pytest.skip("recorded divergence")
    value = UNDEFINED if entry.get("undefined") else entry["input"]
    assert js_date_json(value, TZ) == entry["v8"]


def test_dst_ambiguous_and_gap_are_reproduced_exactly() -> None:
    dates = {entry["id"]: entry for entry in MATRIX["dates"]}
    for case in ("dst_ambiguous", "dst_gap"):
        assert case not in DATE_DIVERGENCES
        assert js_date_json(dates[case]["input"], TZ) == dates[case]["v8"]
    # The ambiguous hour is the earlier instant (CDT), the gap uses CST.
    assert dates["dst_ambiguous"]["v8"] == "2020-11-01T06:30:00.000Z"
    assert dates["dst_gap"]["v8"] == "2020-03-08T08:30:00.000Z"


def test_offsetless_date_time_follows_the_zone_passed_in() -> None:
    # Under UTC the ActiGraph form is read as UTC (research live finding).
    assert (
        js_date_json("2020-02-22T23:01:00.0000000", ZoneInfo("UTC"))
        == "2020-02-22T23:01:00.000Z"
    )
    assert (
        js_date_json("2020-02-22T23:01:00.0000000", TZ) == "2020-02-23T05:01:00.000Z"
    )


def test_explicit_offsets_ignore_the_local_zone() -> None:
    for tz in (TZ, ZoneInfo("UTC"), ZoneInfo("Asia/Tokyo")):
        assert js_date_json("2020-02-22T23:01:00Z", tz) == "2020-02-22T23:01:00.000Z"
        assert js_date_json("2020-02-22", tz) == "2020-02-22T00:00:00.000Z"


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan, 8.64e15 + 1, -8.64e15 - 1])
def test_out_of_range_numbers_are_invalid(value: float) -> None:
    assert js_date_json(value, TZ) is None


# --------------------------------------------------------------------------- #
# The EventNotification argument
# --------------------------------------------------------------------------- #

PROCESSING_COMPLETED = {
    # Frame's documented "Processing Completed" example, keys shuffled.
    "lastEpochSubjectTZ": "2020-02-23T16:57:00.0000000",
    "subjectId": "28953",
    "firstEpochUTC": "2020-02-22T23:01:00.0000000",
    "studyId": "579",
    "firstEpochSubjectTZ": "2020-02-22T17:01:00.0000000",
    "lastEpochUTC": "2020-02-23T22:57:00.0000000",
    "uploadId": "683530",
    "status": "completed",
}


def test_processing_completed_example_serializes_in_frames_key_order() -> None:
    notif = serialize_event_notification(PROCESSING_COMPLETED, TZ)
    assert list(notif) == ["status", "uploadId", "studyId", "subjectId", "start", "end"]
    assert notif == {
        "status": "completed",
        "uploadId": "683530",
        "studyId": "579",
        "subjectId": "28953",
        "start": "2020-02-23T05:01:00.000Z",
        "end": "2020-02-24T04:57:00.000Z",
    }
    # node-celery JSON.stringify output, byte for byte.
    assert json.dumps(notif, separators=(",", ":")) == (
        '{"status":"completed","uploadId":"683530","studyId":"579",'
        '"subjectId":"28953","start":"2020-02-23T05:01:00.000Z",'
        '"end":"2020-02-24T04:57:00.000Z"}'
    )


def test_absent_keys_are_omitted_and_start_end_are_always_present() -> None:
    notif = serialize_event_notification({"status": "completed"}, TZ)
    assert list(notif) == ["status", "start", "end"]
    assert notif["start"] is None and notif["end"] is None


def test_null_values_are_kept_and_null_epochs_are_the_epoch() -> None:
    notif = serialize_event_notification(
        {"status": "completed", "uploadId": None, "subjectId": 5,
         "firstEpochUTC": None, "lastEpochUTC": 1582412460000},
        TZ,
    )
    assert list(notif) == ["status", "uploadId", "subjectId", "start", "end"]
    assert notif["uploadId"] is None
    assert notif["subjectId"] == 5
    assert notif["start"] == "1970-01-01T00:00:00.000Z"
    assert notif["end"] == "2020-02-22T23:01:00.000Z"


def test_non_object_payload_serializes_with_no_copied_keys() -> None:
    # `new EventNotification([])`: every property read is undefined.
    for payload in ([], "hello", 5, True):
        assert serialize_event_notification(payload, TZ) == {"start": None, "end": None}


# --------------------------------------------------------------------------- #
# The zone the route uses
# --------------------------------------------------------------------------- #


def test_local_tz_from_env_reads_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "America/Chicago")
    assert local_tz_from_env() == ZoneInfo("America/Chicago")


@pytest.mark.parametrize("value", [None, ""])
def test_local_tz_from_env_falls_back_to_utc(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("TZ", raising=False)
    else:
        monkeypatch.setenv("TZ", value)
    assert local_tz_from_env() == ZoneInfo("UTC")
