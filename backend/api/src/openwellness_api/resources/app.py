"""App resource — top-level."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import AppRepository
from openwellness_core.domain.models.app import App as AppEntity

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.app import (
    App,
    AppCreate,
    AppList,
    AppUpdate,
)

_COLLECTION = "apps"


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("app")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=App)
    def create(
        body: AppCreate,
        principal: Principal = Depends(get_principal),
        repo: AppRepository = Depends(repo_dep),
    ) -> Any:
        payload = body.model_dump(exclude_unset=False)
        return serialize_one(
            repo.create(AppEntity(**payload)),
            App,
            collection=_COLLECTION,
        )

    @router.get("/{app}", response_model=App)
    def get(
        app: str, repo: AppRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(app, repo), App, collection=_COLLECTION
        )

    @router.patch("/{app}", response_model=App)
    def patch(
        app: str,
        body: AppUpdate,
        principal: Principal = Depends(get_principal),
        repo: AppRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(app, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity), App, collection=_COLLECTION
        )

    @router.delete("/{app}", status_code=204)
    def delete(
        app: str, repo: AppRepository = Depends(repo_dep)
    ) -> None:
        _fetch(app, repo)
        repo.archive(app)
        return None

    @router.post("/{app}:undelete", response_model=App)
    def undelete(
        app: str, repo: AppRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(app, repo)
        repo.unarchive(app)
        return serialize_one(entity, App, collection=_COLLECTION)

    @router.post("/{app}:purge", status_code=204)
    def purge(
        app: str, repo: AppRepository = Depends(repo_dep)
    ) -> None:
        _fetch(app, repo)
        repo.delete(app)
        return None

    @router.get("", response_model=AppList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: AppRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, App, collection=_COLLECTION)
        return {"apps": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
