"""AIP-193 error model and FastAPI exception handlers."""

from .handlers import register_exception_handlers
from .responses import ErrorBody, ErrorResponse

__all__ = ["ErrorBody", "ErrorResponse", "register_exception_handlers"]
