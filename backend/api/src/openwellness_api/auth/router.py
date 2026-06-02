"""AIP-136 custom-method router for the email-OTP auth surface.

Exposes six custom methods under v1's ``/v1`` prefix as
``/v1/auth:sendLoginCode`` etc. FastAPI/Starlette route paths must start with
``/`` and a ``prefix="/auth"`` plus a ``:verb`` route cannot produce
``auth:verb`` — so this router declares NO prefix and gives each route the full
``/auth:<verb>`` path.

The router is deliberately thin: each route resolves an :class:`AuthService`
via :func:`auth_service_dep`, reads the client IP + User-Agent off the request,
delegates to the service, and maps the result dataclass onto a response model.
There is NO flow logic here. The service raises ``HTTPException`` (400 invalid
code / 401 unauthenticated) and lets ``LimitExceededException`` propagate (429);
the registered exception handlers map those — the router never catches them.

Routes are sync ``def`` so FastAPI runs them in a threadpool, which is correct
for the synchronous ``redis``/``smtplib`` collaborators behind the service.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from ..common.handlers import bad_request
from . import errors
from .schemas import (
    PrincipalSummary,
    RefreshResponse,
    RefreshTokenRequest,
    RevokeResponse,
    RevokeTokenRequest,
    SendLoginCodeRequest,
    SendRegistrationCodeRequest,
    TokenResponse,
    UniformSendResponse,
    VerifyLoginCodeRequest,
    VerifyRegistrationCodeRequest,
)
from .service import AuthService


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP: first ``X-Forwarded-For`` hop, else peer addr."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def build_router() -> APIRouter:
    # Imported lazily inside the factory to avoid an import cycle: the auth
    # package's ``__init__`` eagerly imports this router, while
    # ``deps.auth_container`` imports the auth collaborators — a top-level
    # ``auth_service_dep`` import would re-enter a partially-initialized module.
    # By build time (app creation) the container module is fully loaded.
    from ..deps.auth_container import auth_service_dep

    router = APIRouter(tags=["auth"])

    @router.post("/auth:sendLoginCode", response_model=UniformSendResponse)
    def send_login_code(
        request: Request,
        body: SendLoginCodeRequest,
        background_tasks: BackgroundTasks,
        service: AuthService = Depends(auth_service_dep),
    ) -> UniformSendResponse:
        outcome = service.send_login_code(
            email=body.email,
            ip=_client_ip(request),
            tasks=background_tasks,
        )
        return UniformSendResponse(
            message=outcome.message,
            expires_in_seconds=outcome.expires_in_seconds,
            resend_after_seconds=outcome.resend_after_seconds,
        )

    @router.post("/auth:verifyLoginCode", response_model=TokenResponse)
    def verify_login_code(
        request: Request,
        body: VerifyLoginCodeRequest,
        service: AuthService = Depends(auth_service_dep),
    ) -> TokenResponse:
        cred = service.verify_login_code(
            email=body.email,
            code=body.code,
            user_agent=_user_agent(request),
            ip=_client_ip(request),
        )
        return TokenResponse(
            access_token=cred.access_token,
            token_type=cred.token_type,
            expires_in_seconds=cred.expires_in_seconds,
            refresh_token=cred.refresh_token,
            principal=PrincipalSummary(
                user_id=cred.user_id, participant=cred.participant
            ),
        )

    @router.post(
        "/auth:sendRegistrationCode", response_model=UniformSendResponse
    )
    def send_registration_code(
        request: Request,
        body: SendRegistrationCodeRequest,
        background_tasks: BackgroundTasks,
        service: AuthService = Depends(auth_service_dep),
    ) -> UniformSendResponse:
        outcome = service.send_registration_code(
            email=body.email,
            participant_id=body.participant,
            ip=_client_ip(request),
            tasks=background_tasks,
        )
        return UniformSendResponse(
            message=outcome.message,
            expires_in_seconds=outcome.expires_in_seconds,
            resend_after_seconds=outcome.resend_after_seconds,
        )

    @router.post(
        "/auth:verifyRegistrationCode", response_model=TokenResponse
    )
    def verify_registration_code(
        request: Request,
        body: VerifyRegistrationCodeRequest,
        service: AuthService = Depends(auth_service_dep),
    ) -> TokenResponse:
        cred = service.verify_registration_code(
            email=body.email,
            code=body.code,
            user_agent=_user_agent(request),
            ip=_client_ip(request),
        )
        return TokenResponse(
            access_token=cred.access_token,
            token_type=cred.token_type,
            expires_in_seconds=cred.expires_in_seconds,
            refresh_token=cred.refresh_token,
            principal=PrincipalSummary(
                user_id=cred.user_id, participant=cred.participant
            ),
        )

    @router.post("/auth:refreshToken", response_model=RefreshResponse)
    def refresh_token(
        request: Request,
        body: RefreshTokenRequest,
        service: AuthService = Depends(auth_service_dep),
    ) -> RefreshResponse:
        refreshed = service.refresh_token(
            raw_refresh=body.refresh_token,
            user_agent=_user_agent(request),
            ip=_client_ip(request),
        )
        return RefreshResponse(
            access_token=refreshed.access_token,
            token_type=refreshed.token_type,
            expires_in_seconds=refreshed.expires_in_seconds,
            refresh_token=refreshed.refresh_token,
        )

    @router.post("/auth:revokeToken", response_model=RevokeResponse)
    def revoke_token(
        request: Request,
        body: RevokeTokenRequest,
        service: AuthService = Depends(auth_service_dep),
    ) -> RevokeResponse:
        # Precedence: when BOTH all=True and refreshToken are supplied, the
        # all=True branch wins (it is evaluated first; refreshToken is ignored).
        if body.all:
            authorization = request.headers.get("Authorization") or ""
            token = authorization
            if token.startswith("Bearer "):
                token = token[len("Bearer ") :]
            token = token.strip()
            if not token:
                raise errors.unauthenticated()
            service.revoke_all_for_access(access_token=token)
        elif body.refresh_token:
            service.revoke_refresh(raw_refresh=body.refresh_token)
        else:
            raise bad_request(
                "Provide either refreshToken or all=true to revoke."
            )
        return RevokeResponse()

    _ = (
        send_login_code,
        verify_login_code,
        send_registration_code,
        verify_registration_code,
        refresh_token,
        revoke_token,
    )
    return router
