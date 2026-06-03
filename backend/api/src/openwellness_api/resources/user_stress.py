"""UserStress resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import UserStressRepository
from openwellness_core.domain.models.user_stress import UserStress as UserStressEntity

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
from ..schemas.user_stress import (
    UserStress,
    UserStressCreate,
    UserStressList,
    UserStressUpdate,
)

_COLLECTION = "userStresses"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("user_stress")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=UserStress)
    def create(
        user: str,
        body: UserStressCreate,
        principal: Principal = Depends(get_principal),
        repo: UserStressRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(UserStressEntity(**payload)),
            UserStress,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{user_stress}", response_model=UserStress)
    def get(
        user: str, user_stress: str, repo: UserStressRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, user_stress, repo),
            UserStress,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{user_stress}", response_model=UserStress)
    def patch(
        user: str,
        user_stress: str,
        body: UserStressUpdate,
        principal: Principal = Depends(get_principal),
        repo: UserStressRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, user_stress, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            UserStress,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{user_stress}", status_code=204)
    def delete(
        user: str, user_stress: str, repo: UserStressRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, user_stress, repo)
        repo.archive(user_stress)
        return None

    @router.post("/{user_stress}:undelete", response_model=UserStress)
    def undelete(
        user: str, user_stress: str, repo: UserStressRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, user_stress, repo)
        repo.unarchive(user_stress)
        return serialize_one(
            entity,
            UserStress,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{user_stress}:purge", status_code=204)
    def purge(
        user: str, user_stress: str, repo: UserStressRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, user_stress, repo)
        repo.delete(user_stress)
        return None

    @router.get("", response_model=UserStressList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: UserStressRepository = Depends(repo_dep),
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
            UserStress,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"userStresses": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
