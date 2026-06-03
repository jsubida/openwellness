"""Session resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Session(ResourceBase):
    """Session resource."""

    views: list[dict] = []
    session_type: int | None = None
    time_start_in_ms: float = 0.0
    duration_in_ms: float = 0.0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class SessionCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/sessions``."""

    model_config = SCHEMA_CONFIG

    views: list[dict] = []
    session_type: int | None = None
    time_start_in_ms: float = 0.0
    duration_in_ms: float = 0.0
    study_id: str = ""


class SessionUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/sessions/{id}``."""

    model_config = SCHEMA_CONFIG

    views: list[dict] | None = None
    session_type: int | None = None
    time_start_in_ms: float | None = None
    duration_in_ms: float | None = None
    study_id: str | None = None


SessionList = list_response_model("sessions", Session)
