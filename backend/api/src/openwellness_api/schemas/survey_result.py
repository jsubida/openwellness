"""SurveyResult resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class SurveyResult(ResourceBase):
    """SurveyResult resource."""

    survey_date: str
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class SurveyResultCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/surveyResults``."""

    model_config = SCHEMA_CONFIG

    survey_date: str
    study_id: str = ""


class SurveyResultUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/surveyResults/{id}``."""

    model_config = SCHEMA_CONFIG

    survey_date: str | None = None
    study_id: str | None = None


SurveyResultList = list_response_model("surveyResults", SurveyResult)
