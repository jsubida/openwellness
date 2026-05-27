"""Device resource — top-level."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import DeviceRepository
from openwellness_core.domain.models.device import Device as DeviceEntity

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.device import (
    Device,
    DeviceCreate,
    DeviceList,
    DeviceUpdate,
)

_COLLECTION = "devices"


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("device")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=Device)
    def create(
        body: DeviceCreate,
        principal: Principal = Depends(get_principal),
        repo: DeviceRepository = Depends(repo_dep),
    ) -> Any:
        payload = body.model_dump(exclude_unset=False)
        return serialize_one(
            repo.create(DeviceEntity(**payload)),
            Device,
            collection=_COLLECTION,
        )

    @router.get("/{device}", response_model=Device)
    def get(
        device: str, repo: DeviceRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(device, repo), Device, collection=_COLLECTION
        )

    @router.patch("/{device}", response_model=Device)
    def patch(
        device: str,
        body: DeviceUpdate,
        principal: Principal = Depends(get_principal),
        repo: DeviceRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(device, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity), Device, collection=_COLLECTION
        )

    @router.delete("/{device}", status_code=204)
    def delete(
        device: str, repo: DeviceRepository = Depends(repo_dep)
    ) -> None:
        _fetch(device, repo)
        repo.archive(device)
        return None

    @router.post("/{device}:undelete", response_model=Device)
    def undelete(
        device: str, repo: DeviceRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(device, repo)
        repo.unarchive(device)
        return serialize_one(entity, Device, collection=_COLLECTION)

    @router.post("/{device}:purge", status_code=204)
    def purge(
        device: str, repo: DeviceRepository = Depends(repo_dep)
    ) -> None:
        _fetch(device, repo)
        repo.delete(device)
        return None

    @router.get("", response_model=DeviceList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: DeviceRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, Device, collection=_COLLECTION)
        return {"devices": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
