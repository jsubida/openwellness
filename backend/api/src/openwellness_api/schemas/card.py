"""Card resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Card(ResourceBase):
    """Card resource."""

    title: str
    description: str
    url: str
    image: str | None = None
    media_type: int = 0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class CardCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/cards``."""

    model_config = SCHEMA_CONFIG

    title: str
    description: str
    url: str
    image: str | None = None
    media_type: int = 0
    study_id: str = ""


class CardUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/cards/{id}``."""

    model_config = SCHEMA_CONFIG

    title: str | None = None
    description: str | None = None
    url: str | None = None
    image: str | None = None
    media_type: int | None = None
    study_id: str | None = None


CardList = list_response_model("cards", Card)
