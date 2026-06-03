"""AIP-193 error response model.

Wire shape::

    {
      "error": {
        "code": 404,
        "status": "NOT_FOUND",
        "message": "...",
        "details": [...]
      }
    }
"""

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: int
    status: str
    message: str
    details: list[Any] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody


def build_error(
    code: int,
    status: str,
    message: str,
    details: list[Any] | None = None,
) -> dict[str, Any]:
    return ErrorResponse(
        error=ErrorBody(
            code=code, status=status, message=message, details=details or []
        )
    ).model_dump()
