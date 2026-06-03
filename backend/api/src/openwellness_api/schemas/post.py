"""Post resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Post(ResourceBase):
    """Post resource."""

    attachments: list[str]
    conversation_id: str
    content: str
    card: str | None = None
    in_reply_to_id: str | None = None
    replies_count: int = 0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class PostCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/posts``."""

    model_config = SCHEMA_CONFIG

    attachments: list[str]
    conversation_id: str
    content: str
    card: str | None = None
    in_reply_to_id: str | None = None
    replies_count: int = 0
    study_id: str = ""


class PostUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/posts/{id}``."""

    model_config = SCHEMA_CONFIG

    attachments: list[str] | None = None
    conversation_id: str | None = None
    content: str | None = None
    card: str | None = None
    in_reply_to_id: str | None = None
    replies_count: int | None = None
    study_id: str | None = None


PostList = list_response_model("posts", Post)
