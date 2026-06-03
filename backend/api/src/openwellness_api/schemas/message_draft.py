"""MessageDraft resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class MessageDraft(ResourceBase):
    """MessageDraft resource."""

    content: str
    delivery_type: int
    destination: int
    subtype: int
    url: str | None = None
    content2: str | None = None
    day: int | None = None
    week: int | None = None
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class MessageDraftCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/messageDrafts``."""

    model_config = SCHEMA_CONFIG

    content: str
    delivery_type: int
    destination: int
    subtype: int
    url: str | None = None
    content2: str | None = None
    day: int | None = None
    week: int | None = None
    study_id: str = ""


class MessageDraftUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/messageDrafts/{id}``."""

    model_config = SCHEMA_CONFIG

    content: str | None = None
    delivery_type: int | None = None
    destination: int | None = None
    subtype: int | None = None
    url: str | None = None
    content2: str | None = None
    day: int | None = None
    week: int | None = None
    study_id: str | None = None


MessageDraftList = list_response_model("messageDrafts", MessageDraft)
