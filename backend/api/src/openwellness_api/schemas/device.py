"""Device resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class Device(ResourceBase):
    """Device resource."""

    serial_number: str
    platform: str = "unknown"
    participant_id: str | None = None
    is_standard_time: bool | None = None


class DeviceCreate(BaseModel):
    """Body for ``POST /v1/devices``."""

    model_config = SCHEMA_CONFIG

    serial_number: str
    platform: str = "unknown"
    participant_id: str | None = None
    is_standard_time: bool | None = None


class DeviceUpdate(BaseModel):
    """Body for ``PATCH /v1/devices/{id}``."""

    model_config = SCHEMA_CONFIG

    serial_number: str | None = None
    platform: str | None = None
    participant_id: str | None = None
    is_standard_time: bool | None = None


DeviceList = list_response_model("devices", Device)
