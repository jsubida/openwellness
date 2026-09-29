"""ActiGraph webhook value semantics (HOOK-02, D-17).

Frame's ActiGraph route (``api/server/api/event-handlers.js:312-412``) echoes
one request field into a response header and publishes an
``EventNotification`` (``api/server/models/actigraph/eventNotification.js``)
as a Celery task argument. Both are JavaScript behaviors; this module
reproduces them from values captured live from frame and from V8 in the
frame container (``tests/fixtures/frame_actigraph_matrix.json``):

- :func:`js_truthy`: the ``if (request.payload.ValidationCode)`` test.
- :func:`validation_header_value`: what Node writes for
  ``.header('x-actigraph-hook-secret', code)``, or :class:`InvalidHeaderValue`
  where Node's header check throws (hapi 500). CR/LF and other control
  characters are never echoed (T-10-28).
- :func:`js_date_json`: ``JSON.stringify(new Date(x))`` under the container
  ``TZ``. An ActiGraph epoch such as ``2020-02-22T23:01:00.0000000`` has no
  offset, so V8 reads it as *local* time. The consumer does
  ``arrow.get(data['start'])``; a shifted value makes the worker fetch the
  wrong data window with no error (T-10-31).
- :func:`serialize_event_notification`: the object node-celery
  ``JSON.stringify``-s, in frame's key order.

Nothing here logs; the code and the notification never reach a log line.
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

from .hapi import UNDEFINED, js_string

# --------------------------------------------------------------------------- #
# Truthiness
# --------------------------------------------------------------------------- #


def js_truthy(value: object) -> bool:
    """JavaScript ``Boolean(value)`` for a parsed payload value.

    Falsy: ``undefined``, ``null``, ``false``, ``0``/``-0``/``NaN`` and ``""``.
    Everything else is truthy, including ``{}`` and ``[]``, which Python
    treats as false (research Pitfall 8).
    """
    if value is UNDEFINED or value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return not (value == 0 or (isinstance(value, float) and math.isnan(value)))
    if isinstance(value, str):
        return value != ""
    return True


# --------------------------------------------------------------------------- #
# The echoed header
# --------------------------------------------------------------------------- #


class InvalidHeaderValue(ValueError):
    """Node's ``setHeader`` rejected the value, so hapi answers 500.

    The message never carries the value (HIPAA log retention).
    """


# Node's ``checkInvalidHeaderChar``: anything but HTAB, SP..~ and 0x80..0xFF,
# tested on UTF-16 code units. A code point above 0xFF is never valid.
_INVALID_HEADER_CHAR: Final = re.compile(r"[^\t\x20-\x7e\x80-\xff]")


def validation_header_value(code: object) -> tuple[str, ...]:
    """The ``x-actigraph-hook-secret`` lines frame sends for a truthy ``code``.

    Returns one string per header line, ready for Starlette (which encodes
    header values as latin-1), so the wire bytes match frame's:

    - Node validates ``String(code)`` against its header character set and
      throws on anything else: CR, LF, NUL, BEL, DEL and any character
      above U+00FF (captured: hapi 500).
    - A non-string code is written as ``String(code)``: ``123``, ``true``,
      ``[object Object]``.
    - An array is written as one header line per element (``String`` of
      each element, so ``null`` gives ``"null"``); an empty array writes no
      header at all.
    - Frame writes the header block together with its string body as UTF-8,
      so U+0080..U+00FF go out as two bytes each (captured: ``é`` is
      ``C3 A9`` on the wire). The returned strings carry those bytes as
      latin-1 characters.
    """
    if _INVALID_HEADER_CHAR.search(js_string(code)):
        raise InvalidHeaderValue("header value contains an invalid character")
    lines = code if isinstance(code, list) else [code]
    return tuple(_wire(js_string(line)) for line in lines)


def _wire(text: str) -> str:
    return text.encode("utf-8").decode("latin-1")


# --------------------------------------------------------------------------- #
# V8 Date
# --------------------------------------------------------------------------- #

_MAX_TIME_MS: Final = 8.64e15  # ECMAScript TimeClip bound
_MS_PER_DAY: Final = 86_400_000
_MS_PER_400_YEARS: Final = 146_097 * _MS_PER_DAY

# ES date-time format and the V8 legacy forms captured from frame's node:
# ``T``/``t`` or one or more spaces between date and time, seconds and
# fraction optional, any number of fraction digits (truncated to ms),
# ``Z``/``z`` or ``±hh:mm``/``±hhmm``. A date-only form is UTC; a date-time
# with no offset is local time.
_ISO_RE: Final = re.compile(
    r"(?P<year>[+-]\d{6}|\d{4})"
    r"(?:-(?P<month>\d{2})(?:-(?P<day>\d{2})"
    r"(?:(?:[Tt]| +)(?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?"
    r"(?P<offset>[Zz]|[+-]\d{2}:?\d{2})?)?)?)?"
)
# V8's legacy ``YYYY/MM/DD[ hh:mm[:ss[.f]]]``: always local time, date-only
# included (captured: ``2020/02/22`` is local midnight).
_SLASH_RE: Final = re.compile(
    r"(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})"
    r"(?: +(?P<hour>\d{2}):(?P<minute>\d{2})"
    r"(?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?)?"
)
_OFFSET_RE: Final = re.compile(r"([+-])(\d{2}):?(\d{2})")


def js_date_json(value: object, tz: ZoneInfo) -> str | None:
    """``JSON.stringify(new Date(value))`` with the process zone ``tz``.

    ``None`` stands for JSON ``null`` (an invalid Date). ``UNDEFINED`` (a
    missing key) and anything V8 cannot parse give ``None``; JSON ``null``
    is ``0`` ms, so ``1970-01-01T00:00:00.000Z``.
    """
    ms = _js_date_value(value, tz)
    if ms is None or abs(ms) > _MAX_TIME_MS:
        return None
    return _iso_from_epoch_ms(ms)


def _js_date_value(value: object, tz: ZoneInfo) -> int | None:
    """``new Date(value)``'s time value in ms, before TimeClip."""
    if value is UNDEFINED:
        return None
    if value is None:
        return 0  # ToNumber(null)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if abs(value) > _MAX_TIME_MS:
            return None
        return int(math.trunc(value))  # ToIntegerOrInfinity; -0 -> 0
    if isinstance(value, (str, list, dict)):
        # ToPrimitive: an array is joined, an object is "[object Object]".
        return _parse_date_string(js_string(value), tz)
    return None


def _parse_date_string(text: str, tz: ZoneInfo) -> int | None:
    match = _ISO_RE.fullmatch(text)
    local = False
    if match is not None:
        parts = match.groupdict()
        if parts["year"] == "-000000":
            return None
        has_time = parts["hour"] is not None
        local = has_time and parts["offset"] is None
    else:
        match = _SLASH_RE.fullmatch(text)
        if match is None:
            return None
        parts = match.groupdict()
        parts["offset"] = None
        local = True

    year = int(parts["year"])
    month = int(parts["month"] or 1)
    day = int(parts["day"] or 1)
    hour = int(parts["hour"] or 0)
    minute = int(parts["minute"] or 0)
    second = int(parts["second"] or 0)
    millis = int((parts["fraction"] or "0")[:3].ljust(3, "0"))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    if minute > 59 or second > 59:
        return None
    if hour > 24 or (hour == 24 and (minute or second or millis)):
        return None

    # V8 lets a day past the month's end roll over (Feb 30 -> Mar 1), and
    # 24:00 is the next midnight.
    wall = (
        (_days_from_civil(year, month, 1) + day - 1) * _MS_PER_DAY
        + ((hour * 60 + minute) * 60 + second) * 1000
        + millis
    )

    offset = parts["offset"]
    if local:
        offset_ms = _local_offset_ms(wall, tz)
        if offset_ms is None:
            return None
        return wall - offset_ms
    if offset is None or offset in ("Z", "z"):
        return wall
    offset_match = _OFFSET_RE.fullmatch(offset)
    if offset_match is None:
        return None
    sign, hh, mm = offset_match.groups()
    if int(hh) > 23 or int(mm) > 59:
        return None
    offset_ms = (int(hh) * 60 + int(mm)) * 60_000
    return wall - offset_ms if sign == "+" else wall + offset_ms


def _local_offset_ms(wall_ms: int, tz: ZoneInfo) -> int | None:
    """The zone offset V8 applies to a local wall-clock time.

    ``fold=0`` gives V8's choices: the earlier instant for an ambiguous
    (repeated) hour and the pre-transition offset for a time in the gap.

    Python's ``datetime`` covers years 1..9999 only. A wall time outside
    that range is moved by whole 400-year Gregorian cycles (same calendar,
    same weekdays) into it: a BCE time lands before the zone's first
    transition (V8 answers with the zone's earliest offset, LMT for
    Chicago), a time past 9999 in the zone's final recurring rule.
    """
    year = _civil_from_days(wall_ms // _MS_PER_DAY)[0]
    if year < 1:
        wall_ms += -((year - 1) // 400) * _MS_PER_400_YEARS
    elif year > 9999:
        wall_ms -= ((year - 9600) // 400) * _MS_PER_400_YEARS
    try:
        naive = datetime(1970, 1, 1) + timedelta(milliseconds=wall_ms)
    except OverflowError:
        return None
    offset = naive.replace(tzinfo=tz, fold=0).utcoffset()
    if offset is None:
        return None
    return int(offset.total_seconds() * 1000)


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Days since 1970-01-01 in the proleptic Gregorian calendar (any year)."""
    y = year - (1 if month <= 2 else 0)
    era = y // 400  # Python's // floors, so no negative-year adjustment
    yoe = y - era * 400
    mp = (month + 9) % 12
    doy = (153 * mp + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(days: int) -> tuple[int, int, int]:
    z = days + 719468
    era = z // 146097  # floors, as above
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + 3 if mp < 10 else mp - 9
    year = yoe + era * 400 + (1 if month <= 2 else 0)
    return year, month, day


def _iso_from_epoch_ms(ms: int) -> str:
    """``Date.prototype.toISOString``: 4-digit or signed 6-digit years."""
    days, rem = divmod(ms, _MS_PER_DAY)
    year, month, day = _civil_from_days(days)
    hour, rem = divmod(rem, 3_600_000)
    minute, rem = divmod(rem, 60_000)
    second, millis = divmod(rem, 1000)
    if 0 <= year <= 9999:
        year_text = f"{year:04d}"
    else:
        year_text = f"{'+' if year > 0 else '-'}{abs(year):06d}"
    return (
        f"{year_text}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:"
        f"{second:02d}.{millis:03d}Z"
    )


# --------------------------------------------------------------------------- #
# EventNotification
# --------------------------------------------------------------------------- #

_COPIED_KEYS: Final = ("status", "uploadId", "studyId", "subjectId")


def serialize_event_notification(payload: Any, tz: ZoneInfo) -> dict[str, Any]:
    """``JSON.parse(JSON.stringify(new EventNotification(payload)))``.

    Keys in the constructor's order: ``status, uploadId, studyId, subjectId``
    only when present in the payload (an ``undefined`` property is omitted
    by ``JSON.stringify``; ``null`` is kept), then ``start`` and ``end``,
    always present, from ``firstEpochUTC`` and ``lastEpochUTC``.

    ``payload`` must not be ``None``: frame's ``null.status`` throws first.
    A non-object payload reads every property as ``undefined``.
    """
    source: dict[str, Any] = payload if isinstance(payload, dict) else {}
    notif: dict[str, Any] = {
        key: source[key] for key in _COPIED_KEYS if key in source
    }
    notif["start"] = js_date_json(source.get("firstEpochUTC", UNDEFINED), tz)
    notif["end"] = js_date_json(source.get("lastEpochUTC", UNDEFINED), tz)
    return notif


def local_tz_from_env() -> ZoneInfo:
    """The process zone V8 would use: ``TZ``, or UTC when unset or empty.

    ``ow_api`` receives the same ``TZ`` as frame from opserver's ``.env``.
    An unknown zone name raises, so the route answers 500 rather than
    silently publishing a shifted window.
    """
    name = os.environ.get("TZ", "")
    return ZoneInfo(name) if name else ZoneInfo("UTC")
