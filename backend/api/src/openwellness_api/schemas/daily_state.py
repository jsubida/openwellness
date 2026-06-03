"""DailyState resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class DailyState(ResourceBase):
    """DailyState resource."""

    date: str
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class DailyStateCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/dailyStates``."""

    model_config = SCHEMA_CONFIG

    date: str
    study_id: str = ""


class DailyStateUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/dailyStates/{id}``."""

    model_config = SCHEMA_CONFIG

    date: str | None = None
    study_id: str | None = None


DailyStateList = list_response_model("dailyStates", DailyState)
