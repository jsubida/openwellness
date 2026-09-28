"""ActiGraph webhook: ``POST /api/eventHandlers/actigraph`` (HOOK-02).

Reproduces frame's hapi route (``api/server/api/event-handlers.js:312-412``)
at the path registered in the ActiGraph portal, outside the default auth
dependency, with frame's trust model (D-17): no credential and no signature
check. Signature verification is a recorded deferred security finding.

Frame's order:

1. ``validation``: a truthy ``ValidationCode`` (JavaScript truthiness) is the
   subscription handshake: 200 ``Validation Code Received``, ``text/html``,
   the code echoed in ``x-actigraph-hook-secret``. A code Node cannot put in
   a header (CR/LF, control or non-latin-1 characters) is hapi 500.
2. ``notif``: ``status !== 'completed'`` is ``h.close`` (a bare 200).
3. ``device``: ``Device.find({serialNumber: subjectId})[0]``; none is ``h.close``.
4. ``participant``: ``Participant.findById(new ObjectID(device.participantId))``;
   none is ``h.close``, a malformed id is 500.
5. ``requireComponentSetting(Activity)`` on the participant's ``studyId``: 412.
6. ``actigraphObserver``: missing or empty is 412
   ``No value for actigraphObserver``; ``null`` is 500.
7. Publish ``[participant.couchId, EventNotification]`` under the observer
   value (D-01) and ``return ''``: 204 ``text/html`` (research correction to
   D-05; only the handshake answers 200 with a body).

There is no shared state: concurrent handshakes each echo their own code,
and identical notifications each publish, as in frame (no dedupe).

Logging is one failure line with the exception class only. The code, the
notification and every id stay out of the six-year logs (T-10-29); frame's
own ``log.warn`` of the code is deliberately not reproduced.
"""

from __future__ import annotations

from typing import Any, Final

from bson import ObjectId
from fastapi import APIRouter, Request, Response

from ..deps.principal import ALLOW_UNAUTHENTICATED
from .actigraph_notification import (
    js_truthy,
    local_tz_from_env,
    serialize_event_notification,
    validation_header_value,
)
from .hapi import (
    HAPI_HEADERS,
    HTML_UTF8,
    UNDEFINED,
    HapiReply,
    boom,
    closed,
    empty_string,
    js_length,
    js_strict_equals_zero,
    js_string,
)
from .ports import EventHandlerDeps
from .sync_gateway import ACTIVITY, PREFIX, dispatch, publish_observer

ACTIGRAPH_PATH: Final = f"{PREFIX}/actigraph"
ROUTE: Final = "actigraph"
HOOK_SECRET_HEADER: Final = b"x-actigraph-hook-secret"
VALIDATION_BODY: Final = b"Validation Code Received"
OBSERVER: Final = "actigraphObserver"


def validation_received(lines: tuple[str, ...]) -> Response:
    """The handshake answer: 200, frame's body, one header line per value."""
    response = Response(
        content=VALIDATION_BODY,
        status_code=200,
        media_type=HTML_UTF8,
        headers=HAPI_HEADERS,
    )
    for line in lines:
        # Node writes an array value as repeated header lines; latin-1 keeps
        # the bytes validation_header_value prepared (UTF-8, as frame sends).
        response.raw_headers.append((HOOK_SECRET_HEADER, line.encode("latin-1")))
    return response


def _serial_number(source: dict[str, Any]) -> str | None:
    """The device filter value, or ``None`` when no query may be made.

    Deliberate deviation from frame (T-10-32): an absent ``subjectId`` is
    ``undefined``, and Mongoose drops an undefined filter value, so frame's
    ``Device.find({serialNumber: undefined})`` matches every device and
    enqueues a job for whichever participant owns the first one. ow answers
    a bare 200 without querying instead. ``null`` (which only a device
    missing its required ``serialNumber`` could match) and an object or
    array (which Mongoose would read as a query operator or ``$in``) get the
    same bare 200. A number or boolean is cast to a string, as Mongoose's
    ``String`` schema path does.
    """
    value = source.get("subjectId", UNDEFINED)
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return js_string(value)
    return None


def actigraph_core(payload: Any, deps: EventHandlerDeps) -> Response:
    """Frame's pre chain and handler, in frame's order."""
    if payload is None:
        # `request.payload.ValidationCode` on a null payload throws: hapi 500.
        raise TypeError("Cannot read properties of null (reading 'ValidationCode')")
    source: dict[str, Any] = payload if isinstance(payload, dict) else {}

    code = source.get("ValidationCode", UNDEFINED)
    if js_truthy(code):
        return validation_received(validation_header_value(code))

    status = source.get("status", UNDEFINED)
    if not (isinstance(status, str) and status == "completed"):
        return closed()
    notif = serialize_event_notification(payload, local_tz_from_env())

    serial = _serial_number(source)
    if serial is None:
        return closed()
    device = deps.devices.first_by_serial_number(serial)
    if device is None:
        return closed()

    participant = deps.participants.find_by_id(device.get("participantId"))
    if participant is None:
        return closed()

    # `request.pre.participant.studyId`: an ObjectId, which the view key and
    # the 412 message both render as its 24-hex string.
    study_id = participant.get("studyId", UNDEFINED)
    if isinstance(study_id, ObjectId):
        study_id = str(study_id)
    setting = deps.settings.first(None if study_id is UNDEFINED else study_id, ACTIVITY)
    if setting is None:
        raise HapiReply(
            boom(
                412,
                f"Study ({js_string(study_id)}): no component settings of type "
                f"{ACTIVITY}",
            )
        )

    observer = setting.get(OBSERVER, UNDEFINED)
    if observer is None:
        # `null.length` throws before the 412 check: hapi 500.
        raise TypeError("Cannot read properties of null (reading 'length')")
    if observer is UNDEFINED or js_strict_equals_zero(js_length(observer)):
        raise HapiReply(boom(412, f"No value for {OBSERVER}"))

    publish_observer(deps, ROUTE, observer, [participant.get("couchId"), notif])
    return empty_string()


async def _handle(request: Request) -> Response:
    return await dispatch(request, ROUTE, actigraph_core)


def build_actigraph_router() -> APIRouter:
    """The ActiGraph route. ``build_event_handlers_router`` adds the catch-all after it."""
    router = APIRouter()
    # Unauthenticated, as frame's ``auth: false`` (D-17); the route-walking
    # test pins the marker. A literal path, POST only.
    router.post(
        ACTIGRAPH_PATH,
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
        name=ROUTE,
    )(_handle)
    return router
