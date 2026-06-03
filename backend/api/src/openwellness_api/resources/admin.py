"""Admin resource — top-level. Nested ``user`` requires a custom builder."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from openwellness_core.application.repositories import AdminRepository
from openwellness_core.domain.models.admin import Admin as AdminEntity
from openwellness_core.domain.models.admin import AdminUser

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.admin import (
    Admin,
    AdminCreate,
    AdminList,
    AdminUpdate,
)

_COLLECTION = "admins"


def _to_admin_user(body: Any) -> AdminUser:
    if body is None:
        return AdminUser("", "", "")
    return AdminUser(id=body.id, name=body.name, location=body.location)


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("admin")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=Admin)
    def create(
        body: AdminCreate,
        principal: Principal = Depends(get_principal),
        repo: AdminRepository = Depends(repo_dep),
    ) -> Any:
        entity = AdminEntity(
            name=body.name,
            user=_to_admin_user(body.user),
            groups=body.groups,
            study_ids=body.study_ids,
        )
        return serialize_one(repo.create(entity), Admin, collection=_COLLECTION)

    @router.get("/{admin}", response_model=Admin)
    def get(admin: str, repo: AdminRepository = Depends(repo_dep)) -> Any:
        return serialize_one(_fetch(admin, repo), Admin, collection=_COLLECTION)

    @router.patch("/{admin}", response_model=Admin)
    def patch(
        admin: str,
        body: AdminUpdate,
        principal: Principal = Depends(get_principal),
        repo: AdminRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(admin, repo)
        data = body.model_dump(exclude_unset=True)
        if "user" in data and data["user"] is not None:
            data["user"] = _to_admin_user(body.user)
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        return serialize_one(repo.save(entity), Admin, collection=_COLLECTION)

    @router.delete("/{admin}", status_code=204)
    def delete(admin: str, repo: AdminRepository = Depends(repo_dep)) -> None:
        _fetch(admin, repo)
        repo.archive(admin)
        return None

    @router.post("/{admin}:undelete", response_model=Admin)
    def undelete(admin: str, repo: AdminRepository = Depends(repo_dep)) -> Any:
        entity = _fetch(admin, repo)
        repo.unarchive(admin)
        return serialize_one(entity, Admin, collection=_COLLECTION)

    @router.post("/{admin}:purge", status_code=204)
    def purge(admin: str, repo: AdminRepository = Depends(repo_dep)) -> None:
        _fetch(admin, repo)
        repo.delete(admin)
        return None

    @router.get("", response_model=AdminList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: AdminRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, Admin, collection=_COLLECTION)
        return {"admins": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
