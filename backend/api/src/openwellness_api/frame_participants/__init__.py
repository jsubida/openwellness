"""Frame's participant creation at frame's path: ``POST /api/participants``.

* D-11: path-identical and outside ``/v1``, with frame's request and
  response shape (``create.py``, ``documents.py``).
* D-12: the Sync Gateway user is provisioned first; Mongo is written only
  after it exists, and a Mongo failure removes both the Mongo documents and
  the SG user.
* D-13: built, not flipped. The edge's ``/api/participants`` group stays on
  frame for Phase 10; this route is reachable only in-network (the staging
  SC5 proof, 10-13).
* D-14: SG credentials keep frame parity (name = password = couchId); the
  weak credential is a deferred security finding.

Authentication is the router-level ``require_write_principal`` (the
route-walking test sees it; there is no unauthenticated marker), then frame's
``admin`` scope and ``root`` admin group inside the handler.

Recorded deviations from frame:

* D-a: an anonymous caller gets OW's 401 envelope, because the mechanism
  differs (frame: Basic/session ``simple`` strategy; ow: bearer JWT).
  Reconciled when the group flips, alongside WR-07 (D-16).
* D-b: a write failure answers the fixed ``Participant creation failed.``
  where frame's ``Boom.badRequest(error)`` echoes the internal error.
* D-c: ``users.timeCreated`` is the real creation time. (Measured in frame's
  container: Joi 17 calls the ``joistick/new-date`` factory per validation,
  so frame also stamps the real time; the planned "evaluated once at module
  load" premise does not hold, and the two agree.)
"""

from __future__ import annotations

import logging
from functools import cache
from typing import Any

from fastapi import APIRouter, Depends

from openwellness_core.application.repositories.sync_user_repository import (
    SyncUserRepository,
)
from openwellness_core.infrastructure.config.settings import SyncGatewaySettings
from openwellness_core.infrastructure.drivers.sg_admin_user_repository import (
    SGAdminUserRepository,
)

from ..deps.principal import require_write_principal
from .create import PATH, FrameParticipantDeps, create_participant

logger = logging.getLogger(__name__)

__all__ = [
    "FrameParticipantDeps",
    "build_frame_participant_deps",
    "build_frame_participants_router",
]


def build_frame_participants_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_write_principal)])
    router.add_api_route(
        PATH,
        create_participant,
        methods=["POST"],
        include_in_schema=False,
    )
    return router


def build_frame_participant_deps(
    *, db: Any, settings: SyncGatewaySettings | None = None
) -> FrameParticipantDeps:
    """Production deps: the shared Mongo handle and a lazily built SG admin
    repository.

    The admin URL is resolved on first use, so an unset
    ``SYNC_GATEWAY_ADMIN_URL``/``SYNC_GATEWAY_DB`` never blocks boot; only
    this route answers 500. One WARNING at startup names the missing keys,
    never a value.
    """
    sg_settings = settings if settings is not None else SyncGatewaySettings()
    try:
        sg_settings.admin_db_url()
    except ValueError as exc:
        logger.warning("POST /api/participants disabled until set: %s", exc)

    @cache
    def sync_users() -> SyncUserRepository[Any]:
        return SGAdminUserRepository(sg_settings.admin_db_url())

    return FrameParticipantDeps(db=db, sync_users=sync_users)
