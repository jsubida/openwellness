"""FitbitRecord resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class FitbitRecord(ResourceBase):
    """FitbitRecord resource."""

    active_score: int
    activity_calories: int
    calories_bmr: int
    calories_out: int
    distances: list[Any]
    fairly_active_minutes: int
    fitbit_date: str
    lightly_active_minutes: int
    marginal_calories: int
    sedentary_minutes: int
    steps: int
    very_active_minutes: int
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class FitbitRecordCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/fitbitRecords``."""

    model_config = SCHEMA_CONFIG

    active_score: int
    activity_calories: int
    calories_bmr: int
    calories_out: int
    distances: list[Any]
    fairly_active_minutes: int
    fitbit_date: str
    lightly_active_minutes: int
    marginal_calories: int
    sedentary_minutes: int
    steps: int
    very_active_minutes: int
    study_id: str = ""


class FitbitRecordUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/fitbitRecords/{id}``."""

    model_config = SCHEMA_CONFIG

    active_score: int | None = None
    activity_calories: int | None = None
    calories_bmr: int | None = None
    calories_out: int | None = None
    distances: list[Any] | None = None
    fairly_active_minutes: int | None = None
    fitbit_date: str | None = None
    lightly_active_minutes: int | None = None
    marginal_calories: int | None = None
    sedentary_minutes: int | None = None
    steps: int | None = None
    very_active_minutes: int | None = None
    study_id: str | None = None


FitbitRecordList = list_response_model("fitbitRecords", FitbitRecord)
