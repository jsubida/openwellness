"""Sync Gateway ``document_changed`` webhooks (HOOK-01).

Each route reproduces frame's hapi route and pre chain
(``api/server/api/event-handlers.js``, ``api/server/preware.js``):

1. ``requireStudyId``: only a missing ``studyId`` is a 400; ``null`` passes.
2. ``requireComponentSetting(type)``: the oldest StudyComponentSetting, or 412.
3. ``requireObserverName(name)``: the setting's task name, or a 412 that names
   the study (a ``null`` value or a missing study is a TypeError, so 500).
4. Publish frame's exact task name and args (D-01), then ``return null`` (204).

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
    parse_json_payload,
)
from .ports import EventHandlerDeps, get_event_handler_deps

logger = logging.getLogger(__name__)

# api/server/models/mongoose/studyComponent.js cType.
ACTIVITY: Final = 2

PREFIX: Final = "/api/eventHandlers"
FITBIT_HEART_RECORD_PATH: Final = f"{PREFIX}/fitbitHeartRecord"

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
    deps: EventHandlerDeps, setting: dict[str, Any], name: str
) -> Any:
    """``Preware.requireObserverName``: ``setting[name]`` or 412.

    JS order: ``typeof v === 'undefined' || v.length === 0``. A ``null`` value
    throws on ``.length`` before any study lookup.
    """
    value = setting.get(name, UNDEFINED)
    if value is None:
        raise TypeError("Cannot read properties of null (reading 'length')")
    if value is UNDEFINED or js_strict_equals_zero(js_length(value)):
        study = deps.studies.find_by_id(setting.get("studyId"))
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


def observer_core(
    payload: Any,
    deps: EventHandlerDeps,
    *,
    route: str,
    component_type: int,
    observer: str,
    args_of: ArgsOf,
) -> Response:
    """requireStudyId -> requireComponentSetting -> requireObserverName -> publish."""
    study_id = require_study_id(payload)
    setting = require_component_setting(deps, study_id, component_type)
    task_name = require_observer_name(deps, setting, observer)
    publish_observer(deps, route, task_name, args_of(payload))
    return empty_null()


def _owner_only(payload: dict[str, Any]) -> list[Any]:
    # `[payloadDoc.owner]`; a missing owner is undefined -> JSON null.
    return [payload.get("owner")]


async def dispatch(request: Request, route: str, core: Core) -> Response:
    """Parse, read deps, run the synchronous core; any failure is hapi 500."""
    try:
        payload = parse_json_payload(await request.body())
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


def build_sync_gateway_router() -> APIRouter:
    router = APIRouter()

    fitbit_heart_record = _handler(
        "fitbitHeartRecord",
        partial(
            observer_core,
            route="fitbitHeartRecord",
            component_type=ACTIVITY,
            observer="fitbitHeartObserver",
            args_of=_owner_only,
        ),
    )
    router.post(
        FITBIT_HEART_RECORD_PATH,
        openapi_extra={ALLOW_UNAUTHENTICATED: True},
        name="fitbitHeartRecord",
    )(fitbit_heart_record)

    return router
