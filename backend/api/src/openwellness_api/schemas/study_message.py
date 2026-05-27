"""StudyMessage resource schemas (AIP wire shape)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class StudyMessage(ResourceBase):
    """StudyMessage resource."""

    study_id: str
    message: str
    message_type: int
    time_created: datetime | None = None


class StudyMessageCreate(BaseModel):
    """Body for ``POST /v1/studies/{study}/studyMessages``."""

    model_config = SCHEMA_CONFIG

    message: str
    message_type: int
    time_created: datetime


class StudyMessageUpdate(BaseModel):
    """Body for ``PATCH /v1/studies/{study}/studyMessages/{id}``."""

    model_config = SCHEMA_CONFIG

    message: str | None = None
    message_type: int | None = None


StudyMessageList = list_response_model("studyMessages", StudyMessage)
