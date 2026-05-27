"""Map core domain/adapter exceptions onto AIP-193 HTTP responses."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from openwellness_core.application.exceptions import LimitExceededException
from openwellness_core.domain.exceptions.domain_exception import (
    DomainException,
    EntityNotFoundException,
    NotFound,
    UnexpectedCount,
)

from .responses import build_error

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Install handlers on the given app."""

    @app.exception_handler(EntityNotFoundException)
    async def _entity_not_found(_: Request, exc: EntityNotFoundException) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=build_error(404, "NOT_FOUND", str(exc.message)),
        )

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=build_error(404, "NOT_FOUND", str(exc.message)),
        )

    @app.exception_handler(UnexpectedCount)
    async def _unexpected_count(_: Request, exc: UnexpectedCount) -> JSONResponse:
        logger.error(
            "UnexpectedCount: expected=%s actual=%s results=%s",
            exc.expected,
            exc.actual,
            exc.results,
        )
        return JSONResponse(
            status_code=500,
            content=build_error(
                500,
                "INTERNAL",
                f"Unexpected result count (expected {exc.expected}, got {exc.actual})",
            ),
        )

    @app.exception_handler(LimitExceededException)
    async def _limit_exceeded(_: Request, exc: LimitExceededException) -> JSONResponse:
        retry_after = max(int(getattr(exc, "retry_after_secs", 3600)), 1)
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content=build_error(
                429,
                "RESOURCE_EXHAUSTED",
                str(exc),
                details=[{"retry_after_secs": retry_after}],
            ),
        )

    @app.exception_handler(DomainException)
    async def _domain_exception(_: Request, exc: DomainException) -> JSONResponse:
        logger.exception("Unhandled DomainException")
        return JSONResponse(
            status_code=500,
            content=build_error(500, "INTERNAL", str(exc.message)),
        )

    @app.exception_handler(ValidationError)
    async def _pyd_validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=build_error(
                400, "INVALID_ARGUMENT", "Validation failed", details=list(exc.errors())
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=build_error(
                400, "INVALID_ARGUMENT", "Validation failed", details=list(exc.errors())
            ),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        """Unwrap AIP-193 envelopes raised via ``HTTPException(detail=...)``.

        Helpers (``filter``, ``pagination``, ``time_range``) construct the
        envelope inside ``detail`` so it round-trips through FastAPI's
        exception path; this handler returns it as the body directly so
        clients don't see an extra ``{"detail": ...}`` wrap.
        """
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error(
                exc.status_code, "ERROR", str(exc.detail)
            ),
        )
