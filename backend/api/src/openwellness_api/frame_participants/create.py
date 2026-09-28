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
   then the SG user if this request owns it (see :func:`_owns_sync_user`),
   and answers 400 ``Participant creation failed.``
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
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool
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


def sync_user_channels(couch_id: str, study_id: str) -> list[str]:
    """Frame's ``admin_channels`` for a participant's SG user (D-14)."""
    return [couch_id, f"study:{study_id}", SHARED_CHANNEL]


def _is_root_admin(db: Any, principal_id: str) -> bool:
    """``Preware.requireAdminGroup('root')``: ``admin.isMemberOf('root')``."""
    try:
        user_oid = ObjectId(principal_id)
    except (InvalidId, TypeError):
        return False
    user = db["users"].find_one({"_id": user_oid}, {"roles": 1})
    roles = (user or {}).get("roles")
    admin_role = roles.get("admin") if isinstance(roles, dict) else None
    admin_id = admin_role.get("id") if isinstance(admin_role, dict) else None
    if not isinstance(admin_id, str):
        return False
    try:
        admin_oid = ObjectId(admin_id)
    except InvalidId:
        return False
    admin = db["admins"].find_one({"_id": admin_oid}, {"groups": 1})
    groups = (admin or {}).get("groups")
    return isinstance(groups, dict) and "root" in groups


def _fail(step: str, exc: BaseException) -> None:
    logger.error("frame_participants/create failed at %s: %s", step, exc.__class__.__name__)


def _owns_sync_user(
    inserted: list[tuple[str, ObjectId]], sg_created: bool, exc: BaseException
) -> bool:
    """Whether a failed create may delete the SG user it provisioned.

    Provisioning is an upsert, so two creates with the same supplied ``id``
    can both pass the pre-check and provision the same SG user. The unique
    ``participants`` ``_id`` decides which one owns it:

    - this request inserted the participant: it owns the id, and any rival
      fails that insert, so the SG user is its to delete;
    - the participant insert hit a duplicate key: a rival owns the id and
      its SG user, which must survive;
    - the participant insert failed otherwise: delete only a user this
      request created (SG answered 201), never one that already existed.
    """
    if inserted:
        return True
    return sg_created and not isinstance(exc, DuplicateKeyError)


def _compensate(
    db: Any,
    inserted: list[tuple[str, ObjectId]],
    sync_users: SyncUserRepository[Any],
    couch_id: str,
    delete_sync_user: bool,
) -> None:
    """Undo a partial create: inserted Mongo documents (newest first), then
    the SG user when this request owns it. Each step is attempted even if an
    earlier one fails."""
    for collection, oid in reversed(inserted):
        try:
            db[collection].delete_one({"_id": oid})
        except Exception as exc:
            _fail(f"compensate-{collection}-delete", exc)
    if not delete_sync_user:
        logger.warning("frame_participants/create kept the SG user it does not own")
        return
    try:
        sync_users.delete(couch_id)
    except Exception as exc:
        _fail("compensate-sg-delete", exc)


async def create_participant(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> Response:
    """Read the body on the event loop, then run the blocking create (PyMongo,
    bcrypt, the Sync Gateway admin call) in the threadpool, as the event
    handlers do, so a slow SG call never stalls other requests."""
    step = "deps"
    try:
        deps: FrameParticipantDeps = request.app.state.frame_participant_deps

        step = "payload"
        parsed = await read_hapi_payload(request)
        if parsed.response is not None:
            return parsed.response
    except Exception as exc:
        _fail(step, exc)
        return internal()
    return await run_in_threadpool(_create, deps, parsed.payload, principal)


def _create(deps: FrameParticipantDeps, payload: Any, principal: Principal) -> Response:
    """Everything after the payload read, in hapi's order. Blocking."""
    step = "scope"
    try:
        if "admin" not in principal.roles:
            return boom(403, "Insufficient scope")

        step = "validate"
        try:
            body = validate_create_payload(payload)
        except ParticipantValidationError:
            return boom(400, "Invalid request payload input")

        db = deps.db
        step = "admin-group"
        if not _is_root_admin(db, principal.id):
            return boom(403, "Missing required group membership.")

        step = "username-check"
        if db["users"].find_one({"username": body["username"]}, {"_id": 1}) is not None:
            return boom(409, "Username already in use.")

        step = "email-check"
        if db["users"].find_one({"email": body["email"]}, {"_id": 1}) is not None:
            return boom(409, "Email already in use.")

        step = "study-check"
        study_oid = ObjectId(body["studyId"])  # frame's Study.findById throws -> 500
        if db["studies"].find_one({"_id": study_oid}, {"_id": 1}) is None:
            return boom(404, "Study not found for studyId.")

        step = "pid-check"
        if "id" in body:
            pid = ObjectId(body["id"])  # frame's Participant.findById throws -> 500
            if db["participants"].find_one({"_id": pid}, {"_id": 1}) is not None:
                return boom(409, "Participant ID already in use.")
        else:
            pid = ObjectId()
        couch_id = str(pid)

        step = "build"
        now = deps.clock()
        try:
            participant_doc = build_participant_doc(body, pid, study_oid, now)
            user_doc = build_user_doc(body, now)
        except ValueError as exc:
            # Values Joi accepts but frame then fails on mid-create (an
            # uncastable assignedCoachId, a blank participantNumber): refused
            # here, before anything is written anywhere.
            _fail(step, exc)
            return boom(400, CREATION_FAILED)
        user_oid: ObjectId = user_doc["_id"]
        pnum: str = participant_doc["participantNumber"]

        step = "sg-config"
        sync_users = deps.sync_users()

        step = "sg-provision"
        try:
            sg_created = sync_users.provision(
                couch_id, couch_id, sync_user_channels(couch_id, body["studyId"])
            )
        except Exception as exc:
            _fail(step, exc)
            return boom(400, CREATION_FAILED)

        inserted: list[tuple[str, ObjectId]] = []
        try:
            step = "participants-insert"
            db["participants"].insert_one(participant_doc)
            inserted.append(("participants", pid))

            step = "users-insert"
            db["users"].insert_one(user_doc)
            inserted.append(("users", user_oid))

            step = "participants-link-user"
            db["participants"].update_one({"_id": pid}, {"$set": {"userId": user_oid}})

            step = "users-link-participant"
            db["users"].update_one(
                {"_id": user_oid},
                {"$set": {"roles.participant": {"pid": couch_id, "pnum": pnum}}},
            )
        except Exception as exc:
            _fail(step, exc)
            _compensate(
                db, inserted, sync_users, couch_id, _owns_sync_user(inserted, sg_created, exc)
            )
            return boom(400, CREATION_FAILED)

        step = "respond"
        stored_participant = db["participants"].find_one({"_id": pid})
        stored_user = db["users"].find_one({"_id": user_oid})
        if stored_participant is None or stored_user is None:
            raise LookupError("created documents not readable")
        return JSONResponse(
            participant_response(stored_participant, stored_user),
            status_code=200,
            headers=HAPI_HEADERS,
            media_type=JSON_UTF8,
        )
    except Exception as exc:
        _fail(step, exc)
        return internal()
