"""StudyMessage resource — study-scoped (parent has no ``owner`` field)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from openwellness_core.application.repositories import StudyMessageRepository
from openwellness_core.domain.models.study_message import (
    StudyMessage as StudyMessageEntity,
)

from ..common.handlers import (
    apply_patch,
    check_parent,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..common.resource_name import format_name
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.study_message import (
    StudyMessage,
    StudyMessageCreate,
    StudyMessageList,
    StudyMessageUpdate,
)

_COLLECTION = "studyMessages"
_PARENT = "studies"


def _parent_name(study: str) -> str:
    return format_name(collection=_PARENT, id_=study)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{study}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("study_message")

    def _fetch(study: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(study))
        return check_parent(
            entity,
            parent_id=study,
            parent_field="study_id",
            collection=_COLLECTION,
            parent=_PARENT,
        )

    @router.post("", status_code=201, response_model=StudyMessage)
    def create(
        study: str,
        body: StudyMessageCreate,
        principal: Principal = Depends(get_principal),
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> Any:
        payload = body.model_dump(exclude_unset=False)
        payload["study_id"] = study
        return serialize_one(
            repo.create(StudyMessageEntity(**payload)),
            StudyMessage,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.get("/{study_message}", response_model=StudyMessage)
    def get(
        study: str,
        study_message: str,
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> Any:
        return serialize_one(
            _fetch(study, study_message, repo),
            StudyMessage,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.patch("/{study_message}", response_model=StudyMessage)
    def patch(
        study: str,
        study_message: str,
        body: StudyMessageUpdate,
        principal: Principal = Depends(get_principal),
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(study, study_message, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            StudyMessage,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.delete("/{study_message}", status_code=204)
    def delete(
        study: str,
        study_message: str,
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> None:
        _fetch(study, study_message, repo)
        repo.archive(study_message)
        return None

    @router.post("/{study_message}:undelete", response_model=StudyMessage)
    def undelete(
        study: str,
        study_message: str,
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(study, study_message, repo)
        repo.unarchive(study_message)
        return serialize_one(
            entity,
            StudyMessage,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )

    @router.post("/{study_message}:purge", status_code=204)
    def purge(
        study: str,
        study_message: str,
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> None:
        _fetch(study, study_message, repo)
        repo.delete(study_message)
        return None

    @router.get("", response_model=StudyMessageList)
    def list_items(
        study: str,
        params: PageParams = Depends(page_params),
        repo: StudyMessageRepository = Depends(repo_dep),
    ) -> Any:
        # No owner-scoped query method; filter ``list_all`` by study_id.
        items = [s for s in repo.list_all() if getattr(s, "study_id", "") == study]
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            StudyMessage,
            collection=_COLLECTION,
            parent=_parent_name(study),
        )
        return {"studyMessages": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
