"""ParticipantGroup resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class ParticipantGroup(ResourceBase):
    """ParticipantGroup resource."""

    participant_ids: list[str]
    pid_to_mid: dict
    info: dict = {}
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class ParticipantGroupCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/participantGroups``."""

    model_config = SCHEMA_CONFIG

    participant_ids: list[str]
    pid_to_mid: dict
    info: dict = {}
    study_id: str = ""


class ParticipantGroupUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/participantGroups/{id}``."""

    model_config = SCHEMA_CONFIG

    participant_ids: list[str] | None = None
    pid_to_mid: dict | None = None
    info: dict | None = None
    study_id: str | None = None


ParticipantGroupList = list_response_model("participantGroups", ParticipantGroup)
