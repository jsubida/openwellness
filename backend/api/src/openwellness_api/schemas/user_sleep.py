"""UserSleep resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class UserSleep(ResourceBase):
    """UserSleep resource."""

    awake_time: float
    in_bed_time: float
    minutes_awoken: int
    minutes_to_sleep: int
    out_of_bed_time: float
    sleep_date: str
    rating: int
    times_awoken: int
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class UserSleepCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/userSleeps``."""

    model_config = SCHEMA_CONFIG

    awake_time: float
    in_bed_time: float
    minutes_awoken: int
    minutes_to_sleep: int
    out_of_bed_time: float
    sleep_date: str
    rating: int
    times_awoken: int
    study_id: str = ""


class UserSleepUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/userSleeps/{id}``."""

    model_config = SCHEMA_CONFIG

    awake_time: float | None = None
    in_bed_time: float | None = None
    minutes_awoken: int | None = None
    minutes_to_sleep: int | None = None
    out_of_bed_time: float | None = None
    sleep_date: str | None = None
    rating: int | None = None
    times_awoken: int | None = None
    study_id: str | None = None


UserSleepList = list_response_model("userSleeps", UserSleep)
