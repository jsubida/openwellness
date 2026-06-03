"""FitbitHeartRecord resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import FitbitHeartRecordRepository
from openwellness_core.domain.models.fitbit_heart_record import FitbitHeartRecord as FitbitHeartRecordEntity

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
from ..schemas.fitbit_heart_record import (
    FitbitHeartRecord,
    FitbitHeartRecordCreate,
    FitbitHeartRecordList,
    FitbitHeartRecordUpdate,
)

_COLLECTION = "fitbitHeartRecords"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("fitbit_heart_record")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=FitbitHeartRecord)
    def create(
        user: str,
        body: FitbitHeartRecordCreate,
        principal: Principal = Depends(get_principal),
        repo: FitbitHeartRecordRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(FitbitHeartRecordEntity(**payload)),
            FitbitHeartRecord,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{fitbit_heart_record}", response_model=FitbitHeartRecord)
    def get(
        user: str, fitbit_heart_record: str, repo: FitbitHeartRecordRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, fitbit_heart_record, repo),
            FitbitHeartRecord,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{fitbit_heart_record}", response_model=FitbitHeartRecord)
    def patch(
        user: str,
        fitbit_heart_record: str,
        body: FitbitHeartRecordUpdate,
        principal: Principal = Depends(get_principal),
        repo: FitbitHeartRecordRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, fitbit_heart_record, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            FitbitHeartRecord,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{fitbit_heart_record}", status_code=204)
    def delete(
        user: str, fitbit_heart_record: str, repo: FitbitHeartRecordRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, fitbit_heart_record, repo)
        repo.archive(fitbit_heart_record)
        return None

    @router.post("/{fitbit_heart_record}:undelete", response_model=FitbitHeartRecord)
    def undelete(
        user: str, fitbit_heart_record: str, repo: FitbitHeartRecordRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, fitbit_heart_record, repo)
        repo.unarchive(fitbit_heart_record)
        return serialize_one(
            entity,
            FitbitHeartRecord,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{fitbit_heart_record}:purge", status_code=204)
    def purge(
        user: str, fitbit_heart_record: str, repo: FitbitHeartRecordRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, fitbit_heart_record, repo)
        repo.delete(fitbit_heart_record)
        return None

    @router.get("", response_model=FitbitHeartRecordList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: FitbitHeartRecordRepository = Depends(repo_dep),
    ) -> Any:
        rng = resolve_time_range(
            start_time,
            end_time,
            parser=parse_str,
            require=True,
            max_span_days=None,
            default_start="1970-01-01",
            default_end="2100-01-01",
        )
        items = repo.get_for_owner_between(user, rng.start, rng.end)
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            FitbitHeartRecord,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"fitbitHeartRecords": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
