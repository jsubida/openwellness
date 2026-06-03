"""DailyState resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import DailyStateRepository
from openwellness_core.domain.models.daily_state import DailyState as DailyStateEntity

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
from ..common.time_range import parse_str, resolve_time_range
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.daily_state import (
    DailyState,
    DailyStateCreate,
    DailyStateList,
    DailyStateUpdate,
)

_COLLECTION = "dailyStates"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("daily_state")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=DailyState)
    def create(
        user: str,
        body: DailyStateCreate,
        principal: Principal = Depends(get_principal),
        repo: DailyStateRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(DailyStateEntity(**payload)),
            DailyState,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{daily_state}", response_model=DailyState)
    def get(
        user: str, daily_state: str, repo: DailyStateRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, daily_state, repo),
            DailyState,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{daily_state}", response_model=DailyState)
    def patch(
        user: str,
        daily_state: str,
        body: DailyStateUpdate,
        principal: Principal = Depends(get_principal),
        repo: DailyStateRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, daily_state, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            DailyState,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{daily_state}", status_code=204)
    def delete(
        user: str, daily_state: str, repo: DailyStateRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, daily_state, repo)
        repo.archive(daily_state)
        return None

    @router.post("/{daily_state}:undelete", response_model=DailyState)
    def undelete(
        user: str, daily_state: str, repo: DailyStateRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, daily_state, repo)
        repo.unarchive(daily_state)
        return serialize_one(
            entity,
            DailyState,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{daily_state}:purge", status_code=204)
    def purge(
        user: str, daily_state: str, repo: DailyStateRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, daily_state, repo)
        repo.delete(daily_state)
        return None

    @router.get("", response_model=DailyStateList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: DailyStateRepository = Depends(repo_dep),
    ) -> Any:
        rng = resolve_time_range(
            start_time,
            end_time,
            parser=parse_str,
            require=False,
            max_span_days=None,
            default_start="1970-01-01",
            default_end="2100-01-01",
        )
        items = repo.get_for_owner_between(user, rng.start, rng.end)
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            DailyState,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"dailyStates": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
