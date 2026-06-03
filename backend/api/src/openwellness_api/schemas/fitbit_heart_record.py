"""FitbitHeartRecord resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class FitbitHeartRecord(ResourceBase):
    """FitbitHeartRecord resource."""

    fitbit_date: str
    out_of_range: dict
    fat_burn: dict
    cardio: dict
    peak: dict
    custom_heart_rate_zones: list[dict] = []
    resting_heart_rate: int = 0
    zone_minutes: int = 0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class FitbitHeartRecordCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/fitbitHeartRecords``."""

    model_config = SCHEMA_CONFIG

    fitbit_date: str
    out_of_range: dict
    fat_burn: dict
    cardio: dict
    peak: dict
    custom_heart_rate_zones: list[dict] = []
    resting_heart_rate: int = 0
    zone_minutes: int = 0
    study_id: str = ""


class FitbitHeartRecordUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/fitbitHeartRecords/{id}``."""

    model_config = SCHEMA_CONFIG

    fitbit_date: str | None = None
    out_of_range: dict | None = None
    fat_burn: dict | None = None
    cardio: dict | None = None
    peak: dict | None = None
    custom_heart_rate_zones: list[dict] | None = None
    resting_heart_rate: int | None = None
    zone_minutes: int | None = None
    study_id: str | None = None


FitbitHeartRecordList = list_response_model("fitbitHeartRecords", FitbitHeartRecord)
