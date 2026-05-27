"""Condition resource schemas."""

from __future__ import annotations

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Condition(ResourceBase):
    """Condition resource (covers Condition / WeightCondition / LegacyCondition)."""

    app_group: int | None = None
    app_group_note: str | None = None
    week: int | None = None
    weight_goal_level: int | None = None
    weight_loss_protocol: int | None = None
    weight_start_id: str | None = None
    weight_end_id: str | None = None
    was_inactive: bool | None = None
    owner: str = ""
    study_id: str = ""
    updated_by: str = ""


class ConditionCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/conditions``."""

    model_config = SCHEMA_CONFIG

    app_group: int | None = None
    app_group_note: str | None = None
    week: int | None = None
    study_id: str = ""


class WeightConditionCreate(ConditionCreate):
    weight_goal_level: int = 0
    weight_loss_protocol: int = 0
    weight_start_id: str | None = None
    weight_end_id: str | None = None


class LegacyConditionCreate(WeightConditionCreate):
    was_inactive: bool = False


class ConditionUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/conditions/{id}``."""

    model_config = SCHEMA_CONFIG

    app_group: int | None = None
    app_group_note: str | None = None
    week: int | None = None
    weight_goal_level: int | None = None
    weight_loss_protocol: int | None = None
    weight_start_id: str | None = None
    weight_end_id: str | None = None
    was_inactive: bool | None = None


ConditionList = list_response_model("conditions", Condition)
