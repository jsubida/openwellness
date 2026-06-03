"""Parse / validate ``start`` and ``end`` query params for owner-scoped lists.

Required-time-range resources (the high-cardinality time series — Actigraph,
FitbitHeartRecord, FitbitSleep, PhysicalActivity) must constrain queries
to bounded windows. A configurable max-span cap protects the database.
"""

from dataclasses import dataclass
from typing import Any, Callable

import arrow
from arrow import Arrow
from fastapi import HTTPException


@dataclass(frozen=True)
class TimeRange:
    start: Any
    end: Any


def _bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": message,
                "details": [],
            }
        },
    )


def parse_arrow(value: str | None) -> Arrow | None:
    """Parse an ISO-8601 string into an Arrow, or return None."""
    if value is None or value == "":
        return None
    try:
        return arrow.get(value)
    except (arrow.parser.ParserError, ValueError) as e:
        raise _bad_request(f"Invalid timestamp: {value!r} ({e})") from e


def parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as e:
        raise _bad_request(f"Invalid integer: {value!r}") from e


def parse_str(value: str | None) -> str | None:
    """Passthrough parser for date-strings (e.g. ``YYYY-MM-DD``).

    Used by repositories whose ``OwnerArg`` is ``str``.
    """
    return value if value not in (None, "") else None


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError as e:
        raise _bad_request(f"Invalid float: {value!r}") from e


def resolve_time_range(
    start_raw: str | None,
    end_raw: str | None,
    *,
    parser: Callable[[str | None], Any],
    require: bool,
    max_span_days: int | None,
    default_start: Any | None = None,
    default_end: Any | None = None,
) -> TimeRange:
    """Validate a ``start``/``end`` pair under the resource's policy.

    - ``require=True`` rejects requests missing either bound (used for the
      high-cardinality time-series resources).
    - ``max_span_days`` enforces a server-side cap on the requested window;
      only applies when both bounds parse to ``Arrow`` instances.
    - When ``require=False`` and a bound is missing, the corresponding
      default is used; if both default and value are ``None`` the bound is
      passed through as ``None`` (the repository typically interprets that
      as "no bound").
    """
    start = parser(start_raw) if start_raw is not None else default_start
    end = parser(end_raw) if end_raw is not None else default_end

    if require and (start is None or end is None):
        raise _bad_request(
            "start and end query parameters are required for this resource"
        )

    if (
        max_span_days is not None
        and isinstance(start, Arrow)
        and isinstance(end, Arrow)
    ):
        span = (end - start).days
        if span > max_span_days:
            raise _bad_request(
                f"Requested span ({span} days) exceeds maximum "
                f"({max_span_days} days) for this resource"
            )

    return TimeRange(start=start, end=end)
