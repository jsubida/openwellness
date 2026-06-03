"""FitbitSleep resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class FitbitSleep(ResourceBase):
    """FitbitSleep resource."""

    fitbit_date: str
    sleep: list[str]
    stages: dict = {}
    total_minutes_asleep: int = 0
    total_sleep_records: int = 0
    total_time_in_bed: int = 0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class FitbitSleepCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/fitbitSleeps``."""

    model_config = SCHEMA_CONFIG

    fitbit_date: str
    sleep: list[str]
    stages: dict = {}
    total_minutes_asleep: int = 0
    total_sleep_records: int = 0
    total_time_in_bed: int = 0
    study_id: str = ""


class FitbitSleepUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/fitbitSleeps/{id}``."""

    model_config = SCHEMA_CONFIG

    fitbit_date: str | None = None
    sleep: list[str] | None = None
    stages: dict | None = None
    total_minutes_asleep: int | None = None
    total_sleep_records: int | None = None
    total_time_in_bed: int | None = None
    study_id: str | None = None


FitbitSleepList = list_response_model("fitbitSleeps", FitbitSleep)
