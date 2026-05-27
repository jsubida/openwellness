"""JobRule resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class JobRule(ResourceBase):
    """JobRule resource."""

    name: str
    subtype: int
    days_valid: list[int] | None = None
    description: str | None = None
    event_trigger: int | None = None
    processor: str | None = None
    related_subtypes: list[int] | None = None
    time_trigger: int | None = None
    weeks_valid: list[int] | None = None
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class JobRuleCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/jobRules``."""

    model_config = SCHEMA_CONFIG

    name: str
    subtype: int
    days_valid: list[int] | None = None
    description: str | None = None
    event_trigger: int | None = None
    processor: str | None = None
    related_subtypes: list[int] | None = None
    time_trigger: int | None = None
    weeks_valid: list[int] | None = None
    study_id: str = ""


class JobRuleUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/jobRules/{id}``."""

    model_config = SCHEMA_CONFIG

    name: str | None = None
    subtype: int | None = None
    days_valid: list[int] | None = None
    description: str | None = None
    event_trigger: int | None = None
    processor: str | None = None
    related_subtypes: list[int] | None = None
    time_trigger: int | None = None
    weeks_valid: list[int] | None = None
    study_id: str | None = None


JobRuleList = list_response_model("jobRules", JobRule)
