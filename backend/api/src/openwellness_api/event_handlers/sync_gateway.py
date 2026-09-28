"""Sync Gateway ``document_changed`` webhooks (HOOK-01).

Each route reproduces frame's hapi route and pre chain
(``api/server/api/event-handlers.js``, ``api/server/preware.js``):

1. ``requireStudyId``: only a missing ``studyId`` is a 400; ``null`` passes.
2. ``requireComponentSetting(type)``: the oldest StudyComponentSetting, or 412.
3. ``requireObserverName(name)``: the setting's task name, or a 412 that names
   the study (a ``null`` value or a missing study is a TypeError, so 500).
4. Publish frame's exact task name and args (D-01), then ``return null`` (204).

``activity`` and ``weight`` then branch on frame's legacy study list
(``STUDY_SPECIFIC``, see :mod:`.legacy_studies`): a legacy ``activity`` is
never enqueued (D-03), and a SMART ``weight`` reads the participant and its
latest Condition and may enqueue ``jobs.smartRerandomization.waitForWeight``
(D-04, placement 7A).

Handlers only read and publish (D-02). They take the raw ``Request`` and
parse the body themselves: a validated body model would answer 422 in the
OpenWellness envelope instead of hapi's 400/500 (D-05). Dependencies are
read inside the handler's own ``try`` so every failure renders as hapi 500.

Logging carries only the route name and an exception class name, never a
request body, owner id or setting value (HIPAA six-year log retention).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, Final

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from ..deps.principal import ALLOW_UNAUTHENTICATED
from .hapi import (
    UNDEFINED,
    HapiReply,
    boom,
    empty_null,
    internal,
    js_length,
    js_strict_equals_zero,
    js_string,
    read_hapi_payload,
)
from .ports import EventHandlerDeps, get_event_handler_deps

logger = logging.getLogger(__name__)

# api/server/models/mongoose/studyComponent.js cType.
WEIGHT: Final = 1
ACTIVITY: Final = 2
SOCIAL: Final = 4

# processLegacyWeight's task and filters (event-handlers.js:93-137).
SMART_WAIT_FOR_WEIGHT: Final = "jobs.smartRerandomization.waitForWeight"
FTT_BUDDY: Final = 3  # Participant.pType.FTTBuddy (participant.js)

PREFIX: Final = "/api/eventHandlers"
ACTIVITY_PATH: Final = f"{PREFIX}/activity"
FITBIT_HEART_RECORD_PATH: Final = f"{PREFIX}/fitbitHeartRecord"
POST_PATH: Final = f"{PREFIX}/post"
WEIGHT_PATH: Final = f"{PREFIX}/weight"

Core = Callable[[Any, EventHandlerDeps], Response]
ArgsOf = Callable[[dict[str, Any]], list[Any]]


# --------------------------------------------------------------------------- #
# Frame's pre chain, as reusable steps
# --------------------------------------------------------------------------- #


def require_study_id(payload: Any) -> Any:
    """``Preware.requireStudyId``: ``request.payload.studyId`` or 400."""
    if payload is None:
        # `null.studyId` throws in JS: hapi answers 500.
        raise TypeError("Cannot read properties of null (reading 'studyId')")
    if not isinstance(payload, dict) or "studyId" not in payload:
        raise HapiReply(boom(400, "Missing studyId"))
    return payload["studyId"]


def require_component_setting(
    deps: EventHandlerDeps, study_id: Any, component_type: int
) -> dict[str, Any]:
    """``Preware.requireComponentSetting``: ``setting[0]`` or 412."""
    setting = deps.settings.first(study_id, component_type)
    if setting is None:
        raise HapiReply(
            boom(
                412,
                f"Study ({js_string(study_id)}): no component settings of type "
                f"{component_type}",
            )
        )
    return setting


def require_observer_name(
    deps: EventHandlerDeps,
    setting: dict[str, Any],
    name: str,
    *,
    lookup_study_id: Any = UNDEFINED,
) -> Any:
    """``Preware.requireObserverName``: ``setting[name]`` or 412.

    JS order: ``typeof v === 'undefined' || v.length === 0``. A ``null`` value
    throws on ``.length`` before any study lookup.

    The 412 names the study found by ``setting.studyId``. ``weight``'s inline
    ``weightObserver`` pre is the same check except that it looks the study
    up by ``request.payload.studyId``; it passes that as ``lookup_study_id``.
    """
    value = setting.get(name, UNDEFINED)
    if value is None:
        raise TypeError("Cannot read properties of null (reading 'length')")
    if value is UNDEFINED or js_strict_equals_zero(js_length(value)):
        study_id = (
            setting.get("studyId") if lookup_study_id is UNDEFINED else lookup_study_id
        )
        study = deps.studies.find_by_id(study_id)
        if study is None:
            raise TypeError("Cannot read properties of null (reading 'name')")
        study_name = js_string(study.get("name", UNDEFINED))
        raise HapiReply(boom(412, f"Study ({study_name}) has no {name} value"))
    return value


def publish_observer(
    deps: EventHandlerDeps, route: str, task_name: Any, args: list[Any]
) -> None:
    """``client.call(observerName, args)``.

    A non-string task name cannot route to any worker. Frame still answers
    204, so this logs and publishes nothing rather than failing the request.
    """
    if not isinstance(task_name, str):
        logger.error(
            "eventHandlers/%s: observer name is not a string (%s); nothing published",
            route,
            type(task_name).__name__,
        )
        return
    deps.publisher.publish(task_name, args)


def pre_chain(
    payload: Any, deps: EventHandlerDeps, *, component_type: int, observer: str
) -> tuple[Any, Any]:
    """requireStudyId -> requireComponentSetting -> requireObserverName.

    Returns ``(studyId, observer task name)``, frame's
    ``request.payload.studyId`` and ``request.pre.observerName``.
    """
    study_id = require_study_id(payload)
    setting = require_component_setting(deps, study_id, component_type)
    return study_id, require_observer_name(deps, setting, observer)


def observer_core(
    payload: Any,
    deps: EventHandlerDeps,
    *,
    route: str,
    component_type: int,
    observer: str,
    args_of: ArgsOf,
) -> Response:
    """The pre chain, then publish the observer task and ``return null``."""
    _, task_name = pre_chain(
        payload, deps, component_type=component_type, observer=observer
    )
    publish_observer(deps, route, task_name, args_of(payload))
    return empty_null()


def activity_core(payload: Any, deps: EventHandlerDeps) -> Response:
    """``POST /eventHandlers/activity`` (event-handlers.js:139-166)."""
    study_id, task_name = pre_chain(
        payload, deps, component_type=ACTIVITY, observer="activityObserver"
    )
    if deps.legacy_studies.get().contains(study_id):
        # D-03: frame's ``processLegacyActivity`` is dead and deliberately not
        # ported. It never enqueues; it only reads the participant and the
        # latest Condition, then returns ``null``. Its one observable
        # difference is that it returns ``''`` (204 ``text/html``) when a
        # legacy participant has no Condition, and that branch is out of
        # scope. So a legacy study answers 204 with no reads and no task.
        return empty_null()
    publish_observer(deps, "activity", task_name, _owner_only(payload))
    return empty_null()


def weight_core(payload: Any, deps: EventHandlerDeps) -> Response:
    """``POST /eventHandlers/weight`` (event-handlers.js:214-256)."""
    study_id = require_study_id(payload)
    setting = require_component_setting(deps, study_id, WEIGHT)
    # The inline ``weightObserver`` pre: requireObserverName's check, with the
    # 412's study looked up by the payload's studyId, not the setting's.
    task_name = require_observer_name(
        deps, setting, "weightObserver", lookup_study_id=study_id
    )
    legacy = deps.legacy_studies.get()
    if legacy.contains(study_id):
        # processLegacyWeight: only SMART does anything; fit2Thrive and mPower
        # answer null with no reads and no task.
        if legacy.is_smart(study_id):
            smart_weight(payload, deps)
        return empty_null()
    publish_observer(deps, "weight", task_name, _owner_and_id(payload))
    return empty_null()


def smart_weight(payload: dict[str, Any], deps: EventHandlerDeps) -> None:
    """processLegacyWeight's SMART branch (event-handlers.js:105-134).

    D-04 placement decision: Pattern 7A. Frame's SMART "inline work" is all
    reads plus one enqueue, and it writes nothing. So ow keeps those reads
    (D-02 allows reads) and publishes frame's exact task,
    ``jobs.smartRerandomization.waitForWeight [participant _id, weight _id]``,
    which ``router`` already routes (``task_router.py:177``). It is the
    smallest additive change that keeps rollback to frame intact: no
    scheduler PR, no router ``all_tasks`` entry and no worker deploy ahead
    of the SG-4 flip, and the enqueued job is byte-identical to frame's.
    Pattern 7B (a new router-registered scheduler task) was rejected: it puts
    a cross-repo deploy on the critical path with no behavioral gain.

    The filters are frame's, in frame's order, because ``waitForWeight``
    re-checks PENDING and raises otherwise (T-10-25):

    - ``Object.keys(participant)`` on a missing participant throws, so 500;
    - ``isActive === false`` or ``participantType === FTTBuddy``: nothing;
    - no latest Condition: nothing;
    - ``responderState === PENDING`` (0): publish.
    """
    couch_id = payload.get("owner")
    participant = deps.participants.find_by_couch_id(couch_id)
    if participant is None:
        raise TypeError("Cannot convert undefined or null to object")
    if participant.get("isActive") is False:
        return
    if _js_strict_equals_number(participant.get("participantType"), FTT_BUDDY):
        return
    # ``participant._id.toString()``: the ObjectId's 24-hex string.
    participant_id = str(participant["_id"])
    condition = deps.conditions.latest(couch_id)
    if condition is None:
        return
    if js_strict_equals_zero(condition.get("responderState", UNDEFINED)):
        deps.publisher.publish(
            SMART_WAIT_FOR_WEIGHT, [participant_id, payload.get("_id")]
        )


def _js_strict_equals_number(value: object, number: int) -> bool:
    """JavaScript ``value === number`` for a JSON/BSON value."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == number
    )


def _owner_only(payload: dict[str, Any]) -> list[Any]:
    # `[payloadDoc.owner]`; a missing owner is undefined -> JSON null.
    return [payload.get("owner")]


def _owner_and_id(payload: dict[str, Any]) -> list[Any]:
    # `[payloadDoc.owner, payloadDoc._id]`; each missing key -> JSON null.
    return [payload.get("owner"), payload.get("_id")]


async def dispatch(request: Request, route: str, core: Core) -> Response:
    """Parse as hapi does, read deps, run the synchronous core.

    A payload hapi refuses (400/413/415) answers before any lookup; any
    other failure is hapi 500.
    """
    try:
        parsed = await read_hapi_payload(request)
        if parsed.response is not None:
            return parsed.response
        payload = parsed.payload
        deps = get_event_handler_deps(request)
        return await run_in_threadpool(core, payload, deps)
    except HapiReply as reply:
        return reply.response
    except Exception as exc:
        logger.error("eventHandlers/%s failed: %s", route, type(exc).__name__)
        return internal()


def _handler(route: str, core: Core) -> Callable[[Request], Awaitable[Response]]:
    async def handle(request: Request) -> Response:
        return await dispatch(request, route, core)

    return handle


def _register(router: APIRouter, path: str, route: str, core: Core) -> None:
    # Unauthenticated per route, as frame's ``auth: false`` (the route-walking
    # test pins every marker). A literal path, POST only.
    router.post(
        path,
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
        name=route,
    )(_handler(route, core))


def build_sync_gateway_router() -> APIRouter:
    """The SG routes. ``build_event_handlers_router`` adds the catch-all after them."""
    router = APIRouter()
    _register(router, ACTIVITY_PATH, "activity", activity_core)
    _register(
        router,
        FITBIT_HEART_RECORD_PATH,
        "fitbitHeartRecord",
        partial(
            observer_core,
            route="fitbitHeartRecord",
            component_type=ACTIVITY,
            observer="fitbitHeartObserver",
            args_of=_owner_only,
        ),
    )
    _register(
        router,
        POST_PATH,
        "post",
        partial(
            observer_core,
            route="post",
            component_type=SOCIAL,
            observer="postObserver",
            args_of=_owner_and_id,
        ),
    )
    _register(router, WEIGHT_PATH, "weight", weight_core)
    return router
