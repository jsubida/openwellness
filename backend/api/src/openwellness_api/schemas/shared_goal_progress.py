"""SharedGoalProgress resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class SharedGoalProgress(ResourceBase):
    """SharedGoalProgress resource."""

    date: str
    progress: float = 0.0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class SharedGoalProgressCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/sharedGoalProgress``."""

    model_config = SCHEMA_CONFIG

    date: str
    progress: float = 0.0
    study_id: str = ""


class SharedGoalProgressUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/sharedGoalProgress/{id}``."""

    model_config = SCHEMA_CONFIG

    date: str | None = None
    progress: float | None = None
    study_id: str | None = None


SharedGoalProgressList = list_response_model("sharedGoalProgress", SharedGoalProgress)
