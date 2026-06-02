"""Wire schemas for the email-OTP auth surface.

These are Pydantic v2 request/response models for the six auth custom-method
endpoints. They use :data:`SCHEMA_CONFIG` (populate_by_name + camelCase alias
generator + ``extra="ignore"``) so server-side code keeps snake_case while the
wire stays camelCase — but they are NOT :class:`ResourceBase` subclasses: OTP
codes and tokens are not AIP resources, so they carry no ``name`` /
``createTime`` / ``updateTime`` standard fields.

Request validation lives here (email shape via :class:`pydantic.EmailStr`, the
six-digit code via a ``\\d{6}`` pattern) so a malformed body is rejected with a
400 before the router/service ever runs. The participant field accepts either an
AIP resource name (``participants/<pid>``), a bare ``<pid>``, or a ``pid`` key,
and normalises to the bare pid the service expects.
"""

from __future__ import annotations

from pydantic import (
    AliasChoices,
    BaseModel,
    EmailStr,
    Field,
    field_validator,
)

from ..schemas._base import SCHEMA_CONFIG


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class SendLoginCodeRequest(BaseModel):
    """Body for ``POST /v1/auth:sendLoginCode``."""

    model_config = SCHEMA_CONFIG

    email: EmailStr


class VerifyLoginCodeRequest(BaseModel):
    """Body for ``POST /v1/auth:verifyLoginCode``."""

    model_config = SCHEMA_CONFIG

    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class SendRegistrationCodeRequest(BaseModel):
    """Body for ``POST /v1/auth:sendRegistrationCode``.

    ``participant`` accepts an AIP resource name (``participants/<pid>``), a
    bare ``<pid>``, or a ``pid`` key; the validator strips any leading
    ``participants/`` so ``.participant`` is always the bare pid handed to the
    service.
    """

    model_config = SCHEMA_CONFIG

    email: EmailStr
    participant: str = Field(
        validation_alias=AliasChoices("participant", "pid")
    )

    @field_validator("participant", mode="before")
    @classmethod
    def _strip_resource_prefix(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("participants/"):
            return value[len("participants/") :]
        return value


class VerifyRegistrationCodeRequest(BaseModel):
    """Body for ``POST /v1/auth:verifyRegistrationCode``."""

    model_config = SCHEMA_CONFIG

    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class RefreshTokenRequest(BaseModel):
    """Body for ``POST /v1/auth:refreshToken`` (wire: ``refreshToken``)."""

    model_config = SCHEMA_CONFIG

    refresh_token: str


class RevokeTokenRequest(BaseModel):
    """Body for ``POST /v1/auth:revokeToken``.

    Either ``refreshToken`` (revoke one session) or ``all: true`` (revoke every
    session for the bearer-authenticated caller) must be supplied.
    """

    model_config = SCHEMA_CONFIG

    refresh_token: str | None = None
    all: bool = False


# --------------------------------------------------------------------------- #
# Responses (snake_case fields → camelCase on the wire via SCHEMA_CONFIG;
# FastAPI serializes ``response_model`` by_alias by default)
# --------------------------------------------------------------------------- #
class UniformSendResponse(BaseModel):
    """Uniform 200 send result (identical regardless of eligibility)."""

    model_config = SCHEMA_CONFIG

    status: str = "OK"
    message: str
    expires_in_seconds: int
    resend_after_seconds: int


class PrincipalSummary(BaseModel):
    """Caller identity returned alongside a freshly issued credential."""

    model_config = SCHEMA_CONFIG

    user_id: str
    participant: str | None


class TokenResponse(BaseModel):
    """Full credential returned on a successful login/registration verify."""

    model_config = SCHEMA_CONFIG

    access_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int
    refresh_token: str
    principal: PrincipalSummary


class RefreshResponse(BaseModel):
    """New access + rotated refresh returned from ``:refreshToken``."""

    model_config = SCHEMA_CONFIG

    access_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int
    refresh_token: str


class RevokeResponse(BaseModel):
    """Idempotent acknowledgement returned from ``:revokeToken``."""

    model_config = SCHEMA_CONFIG

    status: str = "OK"


__all__ = [
    "PrincipalSummary",
    "RefreshResponse",
    "RefreshTokenRequest",
    "RevokeResponse",
    "RevokeTokenRequest",
    "SendLoginCodeRequest",
    "SendRegistrationCodeRequest",
    "TokenResponse",
    "UniformSendResponse",
    "VerifyLoginCodeRequest",
    "VerifyRegistrationCodeRequest",
]
