"""CPAPSession resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class CPAPSession(ResourceBase):
    """CPAPSession resource."""

    clinical_metrics: dict
    date_of_sleep: str
    device_id: dict
    patient_interface: dict
    receipt_time: str
    resp_events: dict
    session_date: str
    settings: dict
    usage: dict
    leak_threshold: float = 0.4
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class CPAPSessionCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/cpapSessions``."""

    model_config = SCHEMA_CONFIG

    clinical_metrics: dict
    date_of_sleep: str
    device_id: dict
    patient_interface: dict
    receipt_time: str
    resp_events: dict
    session_date: str
    settings: dict
    usage: dict
    leak_threshold: float = 0.4
    study_id: str = ""


class CPAPSessionUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/cpapSessions/{id}``."""

    model_config = SCHEMA_CONFIG

    clinical_metrics: dict | None = None
    date_of_sleep: str | None = None
    device_id: dict | None = None
    patient_interface: dict | None = None
    receipt_time: str | None = None
    resp_events: dict | None = None
    session_date: str | None = None
    settings: dict | None = None
    usage: dict | None = None
    leak_threshold: float | None = None
    study_id: str | None = None


CPAPSessionList = list_response_model("cpapSessions", CPAPSession)
