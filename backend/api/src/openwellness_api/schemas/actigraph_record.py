"""ActigraphRecord resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class ActigraphRecord(ResourceBase):
    """ActigraphRecord resource."""

    timestamp_utc: float
    timestamp_subject_tz: str
    steps: int
    wear: bool
    axis_x_counts: int = 0
    axis_y_counts: int = 0
    axis_z_counts: int = 0
    intensity: float = 0.0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class ActigraphRecordCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/actigraphRecords``."""

    model_config = SCHEMA_CONFIG

    timestamp_utc: float
    timestamp_subject_tz: str
    steps: int
    wear: bool
    axis_x_counts: int = 0
    axis_y_counts: int = 0
    axis_z_counts: int = 0
    intensity: float = 0.0
    study_id: str = ""


class ActigraphRecordUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/actigraphRecords/{id}``."""

    model_config = SCHEMA_CONFIG

    timestamp_utc: float | None = None
    timestamp_subject_tz: str | None = None
    steps: int | None = None
    wear: bool | None = None
    axis_x_counts: int | None = None
    axis_y_counts: int | None = None
    axis_z_counts: int | None = None
    intensity: float | None = None
    study_id: str | None = None


ActigraphRecordList = list_response_model("actigraphRecords", ActigraphRecord)
