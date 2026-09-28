"""Celery producer for the event-handler publisher port (D-01).

Interface skeleton only: the real producer lands with the GREEN commit.
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProducerSettings(BaseSettings):
    """Broker settings, read from opserver's shared ``CELERY_BROKER_URL``."""

    model_config = SettingsConfigDict(env_prefix="CELERY_", extra="ignore")

    broker_url: str = ""


class CeleryTaskPublisher:
    """``TaskPublisher`` onto the ``celery`` queue ``router`` consumes."""

    def __init__(self, settings: ProducerSettings) -> None:
        self._settings = settings

    @property
    def app(self) -> Celery:
        return Celery("stub", broker="memory://", set_as_current=False)

    def publish(self, task_name: str, args: list[Any]) -> None:
        return None
