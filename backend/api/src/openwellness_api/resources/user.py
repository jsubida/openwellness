"""User resource — top-level."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import UserRepository
from openwellness_core.domain.models.user import User as UserEntity

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.user import (
    User,
    UserCreate,
    UserList,
    UserUpdate,
)

_COLLECTION = "users"


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("user")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=User)
    def create(
        body: UserCreate,
        principal: Principal = Depends(get_principal),
        repo: UserRepository = Depends(repo_dep),
    ) -> Any:
        payload = body.model_dump(exclude_unset=False)
        return serialize_one(
            repo.create(UserEntity(**payload)),
            User,
            collection=_COLLECTION,
        )

    @router.get("/{user}", response_model=User)
    def get(
        user: str, repo: UserRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, repo), User, collection=_COLLECTION
        )

    @router.patch("/{user}", response_model=User)
    def patch(
        user: str,
        body: UserUpdate,
        principal: Principal = Depends(get_principal),
        repo: UserRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity), User, collection=_COLLECTION
        )

    @router.delete("/{user}", status_code=204)
    def delete(
        user: str, repo: UserRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, repo)
        repo.archive(user)
        return None

    @router.post("/{user}:undelete", response_model=User)
    def undelete(
        user: str, repo: UserRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, repo)
        repo.unarchive(user)
        return serialize_one(entity, User, collection=_COLLECTION)

    @router.post("/{user}:purge", status_code=204)
    def purge(
        user: str, repo: UserRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, repo)
        repo.delete(user)
        return None

    @router.get("", response_model=UserList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: UserRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, User, collection=_COLLECTION)
        return {"users": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
