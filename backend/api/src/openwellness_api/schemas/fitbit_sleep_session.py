"""FitbitSleepSession resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class FitbitSleepSession(ResourceBase):
    """FitbitSleepSession resource."""

    date_of_sleep: str
    duration: int
    efficiency: int
    info_code: int
    is_main_sleep: bool
    levels: dict
    log_id: int
    minutes_after_wakeup: int
    minutes_asleep: int
    minutes_awake: int
    minutes_to_fall_asleep: int
    sleep_id: str
    sleep_type: str
    start_date: str
    start_time: str
    time_in_bed: int
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class FitbitSleepSessionCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/fitbitSleepSessions``."""

    model_config = SCHEMA_CONFIG

    date_of_sleep: str
    duration: int
    efficiency: int
    info_code: int
    is_main_sleep: bool
    levels: dict
    log_id: int
    minutes_after_wakeup: int
    minutes_asleep: int
    minutes_awake: int
    minutes_to_fall_asleep: int
    sleep_id: str
    sleep_type: str
    start_date: str
    start_time: str
    time_in_bed: int
    study_id: str = ""


class FitbitSleepSessionUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/fitbitSleepSessions/{id}``."""

    model_config = SCHEMA_CONFIG

    date_of_sleep: str | None = None
    duration: int | None = None
    efficiency: int | None = None
    info_code: int | None = None
    is_main_sleep: bool | None = None
    levels: dict | None = None
    log_id: int | None = None
    minutes_after_wakeup: int | None = None
    minutes_asleep: int | None = None
    minutes_awake: int | None = None
    minutes_to_fall_asleep: int | None = None
    sleep_id: str | None = None
    sleep_type: str | None = None
    start_date: str | None = None
    start_time: str | None = None
    time_in_bed: int | None = None
    study_id: str | None = None


FitbitSleepSessionList = list_response_model("fitbitSleepSessions", FitbitSleepSession)
