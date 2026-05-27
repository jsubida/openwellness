"""MetaData resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class MetaData(ResourceBase):
    """MetaData resource."""

    related_id: str
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class MetaDataCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/metaData``."""

    model_config = SCHEMA_CONFIG

    related_id: str
    study_id: str = ""


class MetaDataUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/metaData/{id}``."""

    model_config = SCHEMA_CONFIG

    related_id: str | None = None
    study_id: str | None = None


MetaDataList = list_response_model("metaData", MetaData)
