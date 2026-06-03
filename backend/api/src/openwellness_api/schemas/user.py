"""User resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class User(ResourceBase):
    """User resource."""

    email: str
    is_active: bool
    username: str
    location: str | None = None
    roles: dict = {}


class UserCreate(BaseModel):
    """Body for ``POST /v1/users``."""

    model_config = SCHEMA_CONFIG

    email: str
    is_active: bool
    username: str
    location: str | None = None
    roles: dict = {}


class UserUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{id}``."""

    model_config = SCHEMA_CONFIG

    email: str | None = None
    is_active: bool | None = None
    username: str | None = None
    location: str | None = None
    roles: dict | None = None


UserList = list_response_model("users", User)
