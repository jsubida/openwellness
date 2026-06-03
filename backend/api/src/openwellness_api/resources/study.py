"""Study resource — top-level with AIP-136 ``:lookup`` custom method."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from openwellness_core.application.repositories import StudyRepository
from openwellness_core.domain.models.study import Study as StudyEntity

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.study import (
    Study,
    StudyCreate,
    StudyList,
    StudyLookup,
    StudyUpdate,
)

_COLLECTION = "studies"


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("study")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=Study)
    def create(
        body: StudyCreate,
        principal: Principal = Depends(get_principal),
        repo: StudyRepository = Depends(repo_dep),
    ) -> Any:
        entity = StudyEntity(**body.model_dump(exclude_unset=False))
        return serialize_one(repo.create(entity), Study, collection=_COLLECTION)

    @router.get("/{study}", response_model=Study)
    def get(study: str, repo: StudyRepository = Depends(repo_dep)) -> Any:
        return serialize_one(_fetch(study, repo), Study, collection=_COLLECTION)

    @router.patch("/{study}", response_model=Study)
    def patch(
        study: str,
        body: StudyUpdate,
        principal: Principal = Depends(get_principal),
        repo: StudyRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(study, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(repo.save(entity), Study, collection=_COLLECTION)

    @router.delete("/{study}", status_code=204)
    def delete(study: str, repo: StudyRepository = Depends(repo_dep)) -> None:
        _fetch(study, repo)
        repo.archive(study)
        return None

    @router.post("/{study}:undelete", response_model=Study)
    def undelete(study: str, repo: StudyRepository = Depends(repo_dep)) -> Any:
        entity = _fetch(study, repo)
        repo.unarchive(study)
        return serialize_one(entity, Study, collection=_COLLECTION)

    @router.post("/{study}:purge", status_code=204)
    def purge(study: str, repo: StudyRepository = Depends(repo_dep)) -> None:
        _fetch(study, repo)
        repo.delete(study)
        return None

    @router.get("", response_model=StudyList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: StudyRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, Study, collection=_COLLECTION)
        return {"studies": rows, "nextPageToken": next_token}

    @router.post(":lookup", response_model=Study)
    def lookup(
        body: StudyLookup, repo: StudyRepository = Depends(repo_dep)
    ) -> Any:
        entity = repo.get_by_name(body.name)
        if entity is None:
            not_found(_COLLECTION, body.name)
        return serialize_one(entity, Study, collection=_COLLECTION)

    _ = (create, get, patch, delete, undelete, purge, list_items, lookup)
    return router
