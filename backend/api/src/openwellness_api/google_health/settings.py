"""Google Health authorization settings (opserver ``docs/google-health.md``, "Env keys").

Inside the ``ow_api`` container every key carries the ``GOOGLE_HEALTH_``
prefix: the client id and secret are the shared, unprefixed host keys passed
by name, and opserver maps the ``OW_GOOGLE_HEALTH_*`` host keys onto the rest.

The secrets are declared ``repr=False`` so a settings object that reaches a
log or a traceback never prints one.
"""

from __future__ import annotations

import re
import urllib.parse
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
_CLIENT_ID_SUFFIX: Final = ".apps.googleusercontent.com"
_MIN_SECRET_LENGTH: Final = 32
_SECRETS: Final[tuple[str, ...]] = ("link_secret", "state_secret", "webhook_secret")


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

    @staticmethod
    def required_keys() -> tuple[str, ...]:
        return _REQUIRED

    def missing_keys(self) -> list[str]:
        """Environment names of the unset required keys. Names only, never values."""
        return [
            f"GOOGLE_HEALTH_{name.upper()}" for name in _REQUIRED if not getattr(self, name)
        ]

    def problems(self, auth_signing_secret: str) -> list[str]:
        """Names of the violated rules (T-10.1-75). Never a value.

        ``auth_signing_secret`` is ``ow_api``'s own access-token signing
        secret, compared only to reject its reuse.
        """
        found: list[str] = []
        values = [getattr(self, name) for name in _SECRETS]
        for name, value in zip(_SECRETS, values, strict=True):
            if len(value) < _MIN_SECRET_LENGTH:
                found.append(f"{name}_short")
        present = [value for value in values if value]
        if len(set(present)) != len(present):
            found.append("secrets_not_distinct")
        if auth_signing_secret and auth_signing_secret in present:
            found.append("secret_reuses_api_jwt")
        if not _is_https_origin(self.public_base_url):
            found.append("public_base_url_not_https_origin")
        if (
            not self.client_id.endswith(_CLIENT_ID_SUFFIX)
            or len(self.client_id) == len(_CLIENT_ID_SUFFIX)
        ):
            found.append("client_id_format")
        hold = self.migration_hold.strip()
        if hold and _hold_malformed(hold):
            found.append("migration_hold_malformed")
        return found

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


def _is_https_origin(value: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(value)
        port_ok = parts.port is None or parts.port > 0
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(parts.hostname)
        and parts.username is None
        and parts.password is None
        and port_ok
        and parts.path in ("", "/")
        and not parts.query
        and not parts.fragment
        and "?" not in value
        and "#" not in value
    )
