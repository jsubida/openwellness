"""Message resource schemas."""

from __future__ import annotations

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Message(ResourceBase):
    """Message resource."""

    body: str
    like_state: int = 0
    read_state: int = 0
    opened_at: float | None = None
    message_id: str | None = None
    delivery_date: float | None = None
    subtype: int | None = None
    condition: int | None = None
    tz_offset: int | None = None
    url: str | None = None
    owner: str = ""
    study_id: str = ""
    updated_by: str = ""


class MessageCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/messages``."""

    model_config = SCHEMA_CONFIG

    body: str
    study_id: str = ""
    like_state: int = 0
    read_state: int = 0
    opened_at: float | None = None
    message_id: str | None = None
    delivery_date: float | None = None
    subtype: int | None = None
    condition: int | None = None
    tz_offset: int | None = None
    url: str | None = None


class MessageUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/messages/{id}``."""

    model_config = SCHEMA_CONFIG

    body: str | None = None
    like_state: int | None = None
    read_state: int | None = None
    opened_at: float | None = None
    message_id: str | None = None
    delivery_date: float | None = None
    subtype: int | None = None
    condition: int | None = None
    tz_offset: int | None = None
    url: str | None = None


MessageList = list_response_model("messages", Message)
