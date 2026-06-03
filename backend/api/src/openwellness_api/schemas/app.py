"""App resource schemas (AIP wire shape)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ..common.pagination import list_response_model
from ._base import SCHEMA_CONFIG, ResourceBase


class App(ResourceBase):
    """App resource."""

    display_name: str
    android_package_name: str | None = None
    app_store_id: str | None = None
    ios_bundle_id: str | None = None
    one_signal_app_id: str | None = None


class AppCreate(BaseModel):
    """Body for ``POST /v1/apps``."""

    model_config = SCHEMA_CONFIG

    name: str
    android_package_name: str | None = None
    app_store_id: str | None = None
    ios_bundle_id: str | None = None
    one_signal_app_id: str | None = None


class AppUpdate(BaseModel):
    """Body for ``PATCH /v1/apps/{id}``."""

    model_config = SCHEMA_CONFIG

    name: str | None = None
    android_package_name: str | None = None
    app_store_id: str | None = None
    ios_bundle_id: str | None = None
    one_signal_app_id: str | None = None


AppList = list_response_model("apps", App)
