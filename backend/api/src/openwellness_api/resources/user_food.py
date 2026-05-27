"""UserFood resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import UserFoodRepository
from openwellness_core.domain.models.user_food import UserFood as UserFoodEntity

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
from ..schemas.user_food import (
    UserFood,
    UserFoodCreate,
    UserFoodList,
    UserFoodUpdate,
)

_COLLECTION = "userFoods"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("user_food")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=UserFood)
    def create(
        user: str,
        body: UserFoodCreate,
        principal: Principal = Depends(get_principal),
        repo: UserFoodRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(UserFoodEntity(**payload)),
            UserFood,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{user_food}", response_model=UserFood)
    def get(
        user: str, user_food: str, repo: UserFoodRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, user_food, repo),
            UserFood,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{user_food}", response_model=UserFood)
    def patch(
        user: str,
        user_food: str,
        body: UserFoodUpdate,
        principal: Principal = Depends(get_principal),
        repo: UserFoodRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, user_food, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            UserFood,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{user_food}", status_code=204)
    def delete(
        user: str, user_food: str, repo: UserFoodRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, user_food, repo)
        repo.archive(user_food)
        return None

    @router.post("/{user_food}:undelete", response_model=UserFood)
    def undelete(
        user: str, user_food: str, repo: UserFoodRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, user_food, repo)
        repo.unarchive(user_food)
        return serialize_one(
            entity,
            UserFood,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{user_food}:purge", status_code=204)
    def purge(
        user: str, user_food: str, repo: UserFoodRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, user_food, repo)
        repo.delete(user_food)
        return None

    @router.get("", response_model=UserFoodList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: UserFoodRepository = Depends(repo_dep),
    ) -> Any:
        rng = resolve_time_range(
            start_time,
            end_time,
            parser=parse_arrow,
            require=False,
            max_span_days=None,
            default_start=arrow.Arrow(1970, 1, 1),
            default_end=arrow.Arrow(2100, 1, 1),
        )
        items = repo.get_for_owner_between(user, rng.start, rng.end)
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            UserFood,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"userFoods": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
