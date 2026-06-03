"""FitbitWeight resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class FitbitWeight(ResourceBase):
    """FitbitWeight resource."""

    weight: float
    bmi: float
    date: str
    fitbit_date: str
    log_id: int
    source: str
    time: str
    fat: float = 0.0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class FitbitWeightCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/fitbitWeights``."""

    model_config = SCHEMA_CONFIG

    weight: float
    bmi: float
    date: str
    fitbit_date: str
    log_id: int
    source: str
    time: str
    fat: float = 0.0
    study_id: str = ""


class FitbitWeightUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/fitbitWeights/{id}``."""

    model_config = SCHEMA_CONFIG

    weight: float | None = None
    bmi: float | None = None
    date: str | None = None
    fitbit_date: str | None = None
    log_id: int | None = None
    source: str | None = None
    time: str | None = None
    fat: float | None = None
    study_id: str | None = None


FitbitWeightList = list_response_model("fitbitWeights", FitbitWeight)
