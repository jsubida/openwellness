"""UserStress resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class UserStress(ResourceBase):
    """UserStress resource."""

    rating: int
    stress_date: str
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class UserStressCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/userStresses``."""

    model_config = SCHEMA_CONFIG

    rating: int
    stress_date: str
    study_id: str = ""


class UserStressUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/userStresses/{id}``."""

    model_config = SCHEMA_CONFIG

    rating: int | None = None
    stress_date: str | None = None
    study_id: str | None = None


UserStressList = list_response_model("userStresses", UserStress)
