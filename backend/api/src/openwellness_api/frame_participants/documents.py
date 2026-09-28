"""Frame-shaped documents for ``POST /api/participants`` (RED stub)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId


class ParticipantValidationError(ValueError):
    """The payload fails frame's Joi schema."""


def validate_create_payload(payload: Any) -> dict[str, Any]:
    return {}


def build_participant_doc(
    payload: dict[str, Any], pid: ObjectId, study_oid: ObjectId, now: datetime
) -> dict[str, Any]:
    return {}


def build_user_doc(
    payload: dict[str, Any], now: datetime, user_id: ObjectId | None = None
) -> dict[str, Any]:
    return {}


def hash_password(password: str) -> str:
    return ""


def participant_response(participant_doc: dict[str, Any], user_doc: dict[str, Any]) -> dict[str, Any]:
    return {}
