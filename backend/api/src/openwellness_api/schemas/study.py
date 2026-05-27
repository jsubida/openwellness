"""Study resource schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Study(ResourceBase):
    """Study resource.

    AIP-122: the domain's ``name`` (a human label) lands on the wire as
    ``displayName``; the AIP ``name`` is the resource path.
    """

    app_id: str
    display_name: str = ""
    time_created: datetime | None = None
    description: str | None = None
    end_intervention_week: int = 99999
    time_updated: datetime | None = None
    updated_by: str | None = None


class StudyCreate(BaseModel):
    """Body for ``POST /v1/studies``."""

    model_config = SCHEMA_CONFIG

    app_id: str
    name: str
    """Human-readable label for the study (sent as ``name`` for create)."""
    time_created: datetime
    description: str | None = None
    end_intervention_week: int = 99999
    updated_by: str | None = None


class StudyUpdate(BaseModel):
    """Body for ``PATCH /v1/studies/{study}``."""

    model_config = SCHEMA_CONFIG

    app_id: str | None = None
    name: str | None = None
    description: str | None = None
    end_intervention_week: int | None = None
    updated_by: str | None = None


class StudyLookup(BaseModel):
    """Body for ``POST /v1/studies:lookup``."""

    model_config = ConfigDict(extra="forbid")

    name: str


StudyList = list_response_model("studies", Study)
