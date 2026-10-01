"""Fitbit resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Fitbit(ResourceBase):
    """Fitbit resource.

    ``accessToken`` and ``refreshToken`` are write-only: accepted on create
    and update, never returned. The reads are unauthenticated and the
    collection holds both legacy Fitbit and Google Health OAuth tokens; no
    client reads them over REST (the scheduler reads Mongo directly).
    """

    participant_id: str
    owner_id: str | None = None
    subscription_id: str | None = None


class FitbitCreate(BaseModel):
    """Body for ``POST /v1/fitbits``."""

    model_config = SCHEMA_CONFIG

    participant_id: str
    access_token: str | None = None
    refresh_token: str | None = None
    owner_id: str | None = None
    subscription_id: str | None = None


class FitbitUpdate(BaseModel):
    """Body for ``PATCH /v1/fitbits/{id}``."""

    model_config = SCHEMA_CONFIG

    participant_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    owner_id: str | None = None
    subscription_id: str | None = None


FitbitList = list_response_model("fitbits", Fitbit)
