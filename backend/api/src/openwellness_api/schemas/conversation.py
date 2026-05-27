"""Conversation resource schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Conversation(ResourceBase):
    """Conversation resource."""

    kind: int
    title: str | None = None
    owner: str = ""
    study_id: str = ""
    updated_by: str = ""


class ConversationCreate(BaseModel):
    """Body for ``POST /v1/conversations``."""

    model_config = SCHEMA_CONFIG

    kind: int
    owner: str
    study_id: str = ""
    title: str | None = None


class ConversationUpdate(BaseModel):
    """Body for ``PATCH /v1/conversations/{conversation}``."""

    model_config = SCHEMA_CONFIG

    kind: int | None = None
    title: str | None = None


class ConversationFilterBody(BaseModel):
    """Single filter clause for ``conversations:search``."""

    model_config = SCHEMA_CONFIG

    type: Literal["channels", "kind", "week"]
    val: list[str] | int | str


class ConversationSearchBody(BaseModel):
    """Body for ``POST /v1/conversations:search``."""

    model_config = SCHEMA_CONFIG

    filters: list[ConversationFilterBody]


ConversationList = list_response_model("conversations", Conversation)
