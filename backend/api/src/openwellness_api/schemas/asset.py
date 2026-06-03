"""Asset resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Asset(ResourceBase):
    """Asset resource."""

    source_changed_at: float
    title: str
    url: str
    category: int | None = None
    description: str | None = None
    kind: int | None = None
    media_type: int = 0
    placeholder_url: str | None = None
    week: int | None = None
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class AssetCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/assets``."""

    model_config = SCHEMA_CONFIG

    source_changed_at: float
    title: str
    url: str
    category: int | None = None
    description: str | None = None
    kind: int | None = None
    media_type: int = 0
    placeholder_url: str | None = None
    week: int | None = None
    study_id: str = ""


class AssetUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/assets/{id}``."""

    model_config = SCHEMA_CONFIG

    source_changed_at: float | None = None
    title: str | None = None
    url: str | None = None
    category: int | None = None
    description: str | None = None
    kind: int | None = None
    media_type: int | None = None
    placeholder_url: str | None = None
    week: int | None = None
    study_id: str | None = None


AssetList = list_response_model("assets", Asset)
