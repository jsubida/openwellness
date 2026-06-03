"""Principal (caller identity) dependency.

v1 has no real auth. The owner-scoped factory uses :func:`get_principal`
to stamp ``updated_by`` on writes. Tests can drive this via the
``X-Principal-Id`` header. When auth lands, swap this provider for one
that validates a bearer token, populates roles, etc.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Header


@dataclass(frozen=True)
class Principal:
    """The caller of an API request."""

    id: str
    """A free-form identifier. ``"anonymous"`` if no header was supplied."""


def get_principal(
    x_principal_id: Annotated[str | None, Header(alias="X-Principal-Id")] = None,
) -> Principal:
    return Principal(id=x_principal_id or "anonymous")
