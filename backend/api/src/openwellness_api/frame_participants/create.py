"""``POST /api/participants``: frame's participant creation, SG user first.

Lifecycle, in hapi's order for frame's route (``auth: {strategy: 'simple',
scope: 'admin'}``, ``validate.payload``, ``pre: [requireAdminGroup('root'),
usernameCheck, emailCheck, study, pid]``):

1. the router-level ``require_write_principal`` has already answered 401/403
   for a missing bearer or a client principal header (deviation D-a);
2. payload parse, hapi's 400/413/415;
3. scope: ``admin`` must be one of the principal's roles, else 403
   ``Insufficient scope``;
4. validation, 400 ``Invalid request payload input`` (frame's production
   failAction message);
5. ``requireAdminGroup('root')``: the caller's ``admins`` document must have
   ``root`` among its ``groups`` keys, else 403;
6. username 409, email 409, study 404, supplied id 409;
7. the Sync Gateway user is provisioned FIRST (D-12), with frame's
   credentials (D-14); a failure answers 400 and nothing reaches Mongo;
8. Mongo: insert ``participants``, insert ``users``, ``$set userId``,
   ``$set roles.participant``. Any failure deletes the inserted documents,
   then the SG user, and answers 400 ``Participant creation failed.``
   (deviation D-b: frame echoes the internal error; its concurrent create and
   broken compensation are not reproduced);
9. both documents are re-read and returned in frame's shape.

Log lines name the step and the exception class only: never a password,
hash, email, username, or the couchId (which is the SG password under D-14).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Final

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, Request
from starlette.responses import JSONResponse, Response

from openwellness_core.application.repositories.sync_user_repository import (
    SyncUserRepository,
)

from ..deps.principal import Principal, get_principal
from ..event_handlers.hapi import HAPI_HEADERS, JSON_UTF8, boom, internal, read_hapi_payload
from .documents import (
    ParticipantValidationError,
    build_participant_doc,
    build_user_doc,
    participant_response,
    validate_create_payload,
)

logger = logging.getLogger(__name__)

PATH: Final = "/api/participants"
CREATION_FAILED: Final = "Participant creation failed."
SHARED_CHANNEL: Final = "sharedData"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class FrameParticipantDeps:
    """What the route needs.

    ``db`` is indexable by collection name (a pymongo ``Database`` or the
    core ``MDBCollectionRepository``). ``sync_users`` returns the SG admin
    repository; it is a provider so an unset ``SYNC_GATEWAY_ADMIN_URL`` fails
    this route at use time (500) and never blocks boot (T-10-39).
    """

    db: Any
    sync_users: Callable[[], SyncUserRepository[Any]]
    clock: Callable[[], datetime] = field(default=_utc_now)


async def create_participant(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> Response:
    """RED stub."""
    return internal()
