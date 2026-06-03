"""UserSettings resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class UserSettings(ResourceBase):
    """UserSettings resource."""

    wake_time: float | None = None
    sleep_time: float | None = None
    start_date: float | None = None
    end_study_message: str | None = None
    should_email_notifications: bool = True
    run_in_start_date: float = 0
    study_id: str = ""
    owner: str = ""
    updated_by: str = ""


class UserSettingsCreate(BaseModel):
    """Body for ``POST /v1/users/{user}/userSettings``."""

    model_config = SCHEMA_CONFIG

    wake_time: float | None = None
    sleep_time: float | None = None
    start_date: float | None = None
    end_study_message: str | None = None
    should_email_notifications: bool = True
    run_in_start_date: float = 0
    study_id: str = ""


class UserSettingsUpdate(BaseModel):
    """Body for ``PATCH /v1/users/{user}/userSettings/{id}``."""

    model_config = SCHEMA_CONFIG

    wake_time: float | None = None
    sleep_time: float | None = None
    start_date: float | None = None
    end_study_message: str | None = None
    should_email_notifications: bool | None = None
    run_in_start_date: float | None = None
    study_id: str | None = None


UserSettingsList = list_response_model("userSettings", UserSettings)
