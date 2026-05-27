"""Weight resource schemas (AIP wire shape)."""

from __future__ import annotations

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Weight(ResourceBase):
    """Weight reading for a user."""

    weight: float
    owner: str
    study_id: str = ""
    updated_by: str = ""


class WeightCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/weights``."""

    model_config = SCHEMA_CONFIG

    weight: float
    study_id: str = ""


class WeightUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/weights/{weight}``."""

    model_config = SCHEMA_CONFIG

    weight: float | None = None
    study_id: str | None = None


WeightList = list_response_model("weights", Weight)
