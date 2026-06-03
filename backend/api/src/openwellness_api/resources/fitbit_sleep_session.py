"""FitbitSleepSession resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import FitbitSleepSessionRepository
from openwellness_core.domain.models.fitbit_sleep_session import FitbitSleepSession as FitbitSleepSessionEntity

from ..common.handlers import (
    apply_patch,
    check_parent,
    not_found,
    serialize_many,
    serialize_one,
    stamp_audit,
)
from ..common.pagination import PageParams, page_params, paginate
from ..common.resource_name import format_name
from ..common.time_range import parse_arrow, resolve_time_range
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.fitbit_sleep_session import (
    FitbitSleepSession,
    FitbitSleepSessionCreate,
    FitbitSleepSessionList,
    FitbitSleepSessionUpdate,
)

_COLLECTION = "fitbitSleepSessions"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("fitbit_sleep_session")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=FitbitSleepSession)
    def create(
        user: str,
        body: FitbitSleepSessionCreate,
        principal: Principal = Depends(get_principal),
        repo: FitbitSleepSessionRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(FitbitSleepSessionEntity(**payload)),
            FitbitSleepSession,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{fitbit_sleep_session}", response_model=FitbitSleepSession)
    def get(
        user: str, fitbit_sleep_session: str, repo: FitbitSleepSessionRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, fitbit_sleep_session, repo),
            FitbitSleepSession,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{fitbit_sleep_session}", response_model=FitbitSleepSession)
    def patch(
        user: str,
        fitbit_sleep_session: str,
        body: FitbitSleepSessionUpdate,
        principal: Principal = Depends(get_principal),
        repo: FitbitSleepSessionRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, fitbit_sleep_session, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            FitbitSleepSession,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{fitbit_sleep_session}", status_code=204)
    def delete(
        user: str, fitbit_sleep_session: str, repo: FitbitSleepSessionRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, fitbit_sleep_session, repo)
        repo.archive(fitbit_sleep_session)
        return None

    @router.post("/{fitbit_sleep_session}:undelete", response_model=FitbitSleepSession)
    def undelete(
        user: str, fitbit_sleep_session: str, repo: FitbitSleepSessionRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, fitbit_sleep_session, repo)
        repo.unarchive(fitbit_sleep_session)
        return serialize_one(
            entity,
            FitbitSleepSession,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{fitbit_sleep_session}:purge", status_code=204)
    def purge(
        user: str, fitbit_sleep_session: str, repo: FitbitSleepSessionRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, fitbit_sleep_session, repo)
        repo.delete(fitbit_sleep_session)
        return None

    @router.get("", response_model=FitbitSleepSessionList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: FitbitSleepSessionRepository = Depends(repo_dep),
    ) -> Any:
        rng = resolve_time_range(
            start_time,
            end_time,
            parser=parse_arrow,
            require=True,
            max_span_days=7,
            default_start=arrow.Arrow(1970, 1, 1),
            default_end=arrow.Arrow(2100, 1, 1),
        )
        items = repo.get_for_owner_between(user, rng.start, rng.end)
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            FitbitSleepSession,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"fitbitSleepSessions": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
