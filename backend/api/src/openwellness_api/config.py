"""Application configuration.

Implements ``openwellness_core.infrastructure.config.AppConfigInterface``
so it can be passed straight to the core drivers.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from openwellness_core.infrastructure.config import (
    CouchbaseSettings,
    MongoSettings,
    PostgresSettings,
    StorageBackendSettings,
    SyncGatewaySettings,
)
from openwellness_core.infrastructure.config.app_config import AppConfigInterface


class AppConfig(AppConfigInterface):
    """Concrete config — composes core's protocol-typed sub-settings."""

    def __init__(self) -> None:
        self._storage = StorageBackendSettings()
        self._couchbase = CouchbaseSettings()
        self._sync_gateway = SyncGatewaySettings()
        self._mongo = MongoSettings()
        self._postgres = PostgresSettings()
        if self._storage.storage_backend == "postgres" and not self._postgres.url:
            raise ValueError(
                "STORAGE_BACKEND=postgres requires POSTGRES_URL to be set"
            )

    @property
    def couchbase(self) -> CouchbaseSettings:
        return self._couchbase

    @property
    def sync_gateway(self) -> SyncGatewaySettings:
        return self._sync_gateway

    @property
    def mongo(self) -> MongoSettings:
        return self._mongo

    @property
    def postgres(self) -> PostgresSettings:
        return self._postgres

    @property
    def storage_backend(self) -> str:
        return self._storage.storage_backend


class APISettings(BaseSettings):
    """API-only knobs (not part of the core config interface)."""

    model_config = SettingsConfigDict(env_prefix="API_", extra="ignore")

    title: str = "OpenWellness API"
    default_page_size: int = Field(default=50, ge=1, le=1000)
    max_page_size: int = Field(default=1000, ge=1, le=10000)
    time_range_max_span_days: int = 7
    # CORS — comma-separated allowed browser origins for the dashboard SPA.
    # Kept as a plain ``str`` (not ``list[str]``): pydantic-settings parses a
    # bare ``list[str]`` env value as JSON, which breaks a comma-separated
    # ``API_CORS_ALLOWED_ORIGINS``.
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


class RedisSettings(BaseSettings):
    """Redis connection settings (used for OTP / rate-limit caching)."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    url: str = "redis://localhost:6379/0"


class SmtpSettings(BaseSettings):
    """Outbound SMTP settings for email delivery."""

    model_config = SettingsConfigDict(env_prefix="SMTP_", extra="ignore")

    host: str = ""
    port: int = Field(default=587, ge=1, le=65535)
    username: str = ""
    password: str = ""
    use_tls: bool = True
    from_address: str = ""


class AuthSettings(BaseSettings):
    """Authentication knobs: JWT, OTP, rate limits, and misc behaviour flags."""

    model_config = SettingsConfigDict(env_prefix="API_AUTH_", extra="ignore")

    # JWT
    jwt_secret: str = ""
    jwt_alg: str = "HS256"
    jwt_issuer: str = "openwellness-api"
    jwt_audience: str = "openwellness-api"
    access_ttl_seconds: int = 900
    refresh_ttl_seconds: int = 2592000
    jwt_leeway_seconds: int = 30
    # OTP
    otp_ttl_seconds: int = 600
    otp_length: int = 6
    otp_max_attempts: int = Field(default=5, ge=1)
    # Rate limits
    send_window_seconds: int = 3600
    send_max_per_window: int = 5
    resend_cooldown_seconds: int = 60
    ip_window_seconds: int = 3600
    ip_max_per_window: int = 20
    # Behaviour
    enforce_principal: bool = False
    refresh_collection: str = "auth_refresh_sessions"
    code_pepper: str = ""
    legacy_verified_id_salt: str | None = None
