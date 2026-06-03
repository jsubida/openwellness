"""Condition resource — owner-scoped, base-shape Create with int owner-arg."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import ConditionRepository
from openwellness_core.domain.models.condition import (
    Condition as ConditionEntity,
    LegacyCondition,
    WeightCondition,
)

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
from ..common.time_range import parse_int, resolve_time_range
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.condition import (
    Condition,
    ConditionCreate,
    ConditionList,
    ConditionUpdate,
    LegacyConditionCreate,
    WeightConditionCreate,
)

_COLLECTION = "conditions"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def _build_condition(body: Any, user: str, principal: Principal) -> ConditionEntity:
    payload = stamp_audit(
        body.model_dump(exclude_unset=False), parent_id=user, principal=principal
    )
    if isinstance(body, LegacyConditionCreate):
        cls: type[ConditionEntity] = LegacyCondition
    elif isinstance(body, WeightConditionCreate):
        cls = WeightCondition
    else:
        cls = ConditionEntity
    return cls(**payload)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("condition")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=Condition)
    def create(
        user: str,
        body: ConditionCreate,
        principal: Principal = Depends(get_principal),
        repo: ConditionRepository = Depends(repo_dep),
    ) -> Any:
        return serialize_one(
            repo.create(_build_condition(body, user, principal)),
            Condition,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{condition}", response_model=Condition)
    def get(
        user: str, condition: str, repo: ConditionRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, condition, repo),
            Condition,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{condition}", response_model=Condition)
    def patch(
        user: str,
        condition: str,
        body: ConditionUpdate,
        principal: Principal = Depends(get_principal),
        repo: ConditionRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, condition, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            Condition,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{condition}", status_code=204)
    def delete(
        user: str, condition: str, repo: ConditionRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, condition, repo)
        repo.archive(condition)
        return None

    @router.post("/{condition}:undelete", response_model=Condition)
    def undelete(
        user: str, condition: str, repo: ConditionRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, condition, repo)
        repo.unarchive(condition)
        return serialize_one(
            entity, Condition, collection=_COLLECTION, parent=_parent_name(user)
        )

    @router.post("/{condition}:purge", status_code=204)
    def purge(
        user: str, condition: str, repo: ConditionRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, condition, repo)
        repo.delete(condition)
        return None

    @router.get("", response_model=ConditionList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: ConditionRepository = Depends(repo_dep),
    ) -> Any:
        rng = resolve_time_range(
            start_time,
            end_time,
            parser=parse_int,
            require=False,
            max_span_days=None,
            default_start=0,
            default_end=99999,
        )
        results = repo.get_for_owner_between(user, rng.start, rng.end)
        window, next_token = paginate(results, params)
        rows = serialize_many(
            window, Condition, collection=_COLLECTION, parent=_parent_name(user)
        )
        return {"conditions": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
