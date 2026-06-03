"""StudySettings resource — owner-scoped (studies-parented)."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import StudySettingsRepository
from openwellness_core.domain.models.study_settings import StudySettings as StudySettingsEntity

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
from ..schemas.study_settings import (
    StudySettings,
    StudySettingsCreate,
    StudySettingsList,
    StudySettingsUpdate,
)

_COLLECTION = "studySettings"
_PARENT = "studies"


def _parent_name(study: str) -> str:
    return format_name(collection=_PARENT, id_=study)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{study}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("study_settings")

    def _fetch(study: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(study))
        return check_parent(
            entity, parent_id=study, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=StudySettings)
    def create(
        study: str,
        body: StudySettingsCreate,
        principal: Principal = Depends(get_principal),
        repo: StudySettingsRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=study,
            principal=principal,
        )
        return serialize_one(
            repo.create(StudySettingsEntity(**payload)),
            StudySettings,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.get("/{study_settings}", response_model=StudySettings)
    def get(
        study: str, study_settings: str, repo: StudySettingsRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(study, study_settings, repo),
            StudySettings,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.patch("/{study_settings}", response_model=StudySettings)
    def patch(
        study: str,
        study_settings: str,
        body: StudySettingsUpdate,
        principal: Principal = Depends(get_principal),
        repo: StudySettingsRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(study, study_settings, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            StudySettings,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.delete("/{study_settings}", status_code=204)
    def delete(
        study: str, study_settings: str, repo: StudySettingsRepository = Depends(repo_dep)
    ) -> None:
        _fetch(study, study_settings, repo)
        repo.archive(study_settings)
        return None

    @router.post("/{study_settings}:undelete", response_model=StudySettings)
    def undelete(
        study: str, study_settings: str, repo: StudySettingsRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(study, study_settings, repo)
        repo.unarchive(study_settings)
        return serialize_one(
            entity,
            StudySettings,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.post("/{study_settings}:purge", status_code=204)
    def purge(
        study: str, study_settings: str, repo: StudySettingsRepository = Depends(repo_dep)
    ) -> None:
        _fetch(study, study_settings, repo)
        repo.delete(study_settings)
        return None

    @router.get("", response_model=StudySettingsList)
    def list_items(
        study: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: StudySettingsRepository = Depends(repo_dep),
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
        items = repo.get_for_owner_between(study, rng.start, rng.end)
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            StudySettings,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )
        return {"studySettings": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
