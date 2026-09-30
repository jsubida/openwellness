"""Google Health authorization settings (opserver ``docs/google-health.md``, "Env keys").

Inside the ``ow_api`` container every key carries the ``GOOGLE_HEALTH_``
prefix: the client id and secret are the shared, unprefixed host keys passed
by name, and opserver maps the ``OW_GOOGLE_HEALTH_*`` host keys onto the rest.

The secrets are declared ``repr=False`` so a settings object that reaches a
log or a traceback never prints one.
"""

from __future__ import annotations

import re
from typing import Final, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SCOPES: Final[tuple[str, ...]] = (
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/googlehealth.settings.readonly",
)
"""The four locked read-only scopes (contract "Scopes", D-18)."""

FINISH_AUTH_PATH: Final = "/api/googleHealth/finishAuth"
AUTHORIZE_PATH: Final = "/api/googleHealth/authorize"

_REQUIRED: Final[tuple[str, ...]] = (
    "client_id",
    "client_secret",
    "link_secret",
    "state_secret",
    "webhook_secret",
    "public_base_url",
)

_STUDY_ID = re.compile(r"^[0-9a-fA-F]{24}$")


class GoogleHealthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOOGLE_HEALTH_", extra="ignore")

    client_id: str = ""
    client_secret: str = Field(default="", repr=False)
    link_secret: str = Field(default="", repr=False)
    state_secret: str = Field(default="", repr=False)
    webhook_secret: str = Field(default="", repr=False)
    public_base_url: str = ""
    migration_hold: str = ""

    link_ttl_seconds: int = 259200
    state_ttl_seconds: int = 900
    lock_ttl_ms: int = 60000
    scopes: tuple[str, ...] = DEFAULT_SCOPES

    authorize_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint: str = "https://oauth2.googleapis.com/token"
    revoke_endpoint: str = "https://oauth2.googleapis.com/revoke"
    identity_url: str = "https://health.googleapis.com/v4/users/me/identity"

    def redirect_uri(self) -> str:
        """The registered OAuth redirect URI (contract "Origins")."""
        return self.public_base_url.rstrip("/") + FINISH_AUTH_PATH

    def authorize_url(self) -> str:
        """Base of the staff link: ``<origin>/api/googleHealth/authorize``."""
        return self.public_base_url.rstrip("/") + AUTHORIZE_PATH

    def missing_keys(self) -> list[str]:
        """Environment names of the unset required keys. Names only, never values."""
        return [
            f"GOOGLE_HEALTH_{name.upper()}" for name in _REQUIRED if not getattr(self, name)
        ]

    def held_study_ids(self) -> frozenset[str] | Literal["*"]:
        """The migration hold: ``"*"`` for every study, else the held study ids.

        A malformed value holds every study (fail closed); ``problems`` names
        it, and the routes answer 503 until it is fixed.
        """
        raw = self.migration_hold.strip()
        if not raw:
            return frozenset()
        if _hold_malformed(raw):
            return "*"
        if raw == "*":
            return "*"
        return frozenset(item.strip().lower() for item in raw.split(","))


def _hold_malformed(raw: str) -> bool:
    if raw == "*":
        return False
    items = [item.strip() for item in raw.split(",")]
    return any(not _STUDY_ID.match(item) for item in items)
