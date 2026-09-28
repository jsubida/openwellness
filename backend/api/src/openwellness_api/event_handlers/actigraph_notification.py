"""ActiGraph value semantics (stub; implemented in the GREEN commit)."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo


class InvalidHeaderValue(ValueError):
    """Node's header-value check rejected the code: hapi answers 500."""


def js_truthy(value: object) -> bool:
    return bool(value)


def validation_header_value(code: object) -> tuple[str, ...]:
    return ()


def js_date_json(value: object, tz: ZoneInfo) -> str | None:
    return None


def serialize_event_notification(payload: Any, tz: ZoneInfo) -> dict[str, Any]:
    return {}


def local_tz_from_env() -> ZoneInfo:
    return ZoneInfo("UTC")
