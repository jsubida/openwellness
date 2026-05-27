"""PhysicalActivity resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class PhysicalActivity(ResourceBase):
    """PhysicalActivity resource."""

    activity_id: str
    name: str
    item_description: str
    minutes: int
    intensity: int
    date_of_activity: float
    enjoyment: int
    met: float
    steps: int = 0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class PhysicalActivityCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/physicalActivities``."""

    model_config = SCHEMA_CONFIG

    activity_id: str
    name: str
    item_description: str
    minutes: int
    intensity: int
    date_of_activity: float
    enjoyment: int
    met: float
    steps: int = 0
    study_id: str = ""


class PhysicalActivityUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/physicalActivities/{id}``."""

    model_config = SCHEMA_CONFIG

    activity_id: str | None = None
    name: str | None = None
    item_description: str | None = None
    minutes: int | None = None
    intensity: int | None = None
    date_of_activity: float | None = None
    enjoyment: int | None = None
    met: float | None = None
    steps: int | None = None
    study_id: str | None = None


PhysicalActivityList = list_response_model("physicalActivities", PhysicalActivity)
