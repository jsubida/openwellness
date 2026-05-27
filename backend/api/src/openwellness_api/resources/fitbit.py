"""Fitbit resource — top-level."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import FitbitRepository
from openwellness_core.domain.models.fitbit import Fitbit as FitbitEntity

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.fitbit import (
    Fitbit,
    FitbitCreate,
    FitbitList,
    FitbitUpdate,
)

_COLLECTION = "fitbits"


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("fitbit")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=Fitbit)
    def create(
        body: FitbitCreate,
        principal: Principal = Depends(get_principal),
        repo: FitbitRepository = Depends(repo_dep),
    ) -> Any:
        payload = body.model_dump(exclude_unset=False)
        return serialize_one(
            repo.create(FitbitEntity(**payload)),
            Fitbit,
            collection=_COLLECTION,
        )

    @router.get("/{fitbit}", response_model=Fitbit)
    def get(
        fitbit: str, repo: FitbitRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(fitbit, repo), Fitbit, collection=_COLLECTION
        )

    @router.patch("/{fitbit}", response_model=Fitbit)
    def patch(
        fitbit: str,
        body: FitbitUpdate,
        principal: Principal = Depends(get_principal),
        repo: FitbitRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(fitbit, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity), Fitbit, collection=_COLLECTION
        )

    @router.delete("/{fitbit}", status_code=204)
    def delete(
        fitbit: str, repo: FitbitRepository = Depends(repo_dep)
    ) -> None:
        _fetch(fitbit, repo)
        repo.archive(fitbit)
        return None

    @router.post("/{fitbit}:undelete", response_model=Fitbit)
    def undelete(
        fitbit: str, repo: FitbitRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(fitbit, repo)
        repo.unarchive(fitbit)
        return serialize_one(entity, Fitbit, collection=_COLLECTION)

    @router.post("/{fitbit}:purge", status_code=204)
    def purge(
        fitbit: str, repo: FitbitRepository = Depends(repo_dep)
    ) -> None:
        _fetch(fitbit, repo)
        repo.delete(fitbit)
        return None

    @router.get("", response_model=FitbitList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: FitbitRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, Fitbit, collection=_COLLECTION)
        return {"fitbits": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
