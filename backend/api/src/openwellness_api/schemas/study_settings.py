"""StudySettings resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class StudySettings(ResourceBase):
    """StudySettings resource."""

    goals: list[int] = []
    fitbit_activity: bool = True
    principal_investigator: str | None = None
    owner: str = ""
    study_id: str = ""
    updated_by: str = ""


class StudySettingsCreate(BaseModel):
    """Body for ``POST /v1/studies/{study}/studySettings``."""

    model_config = SCHEMA_CONFIG

    goals: list[int] = []
    fitbit_activity: bool = True
    principal_investigator: str | None = None


class StudySettingsUpdate(BaseModel):
    """Body for ``PATCH /v1/studies/{study}/studySettings/{id}``."""

    model_config = SCHEMA_CONFIG

    goals: list[int] | None = None
    fitbit_activity: bool | None = None
    principal_investigator: str | None = None


StudySettingsList = list_response_model("studySettings", StudySettings)
