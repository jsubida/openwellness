"""Session resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import SessionRepository
from openwellness_core.domain.models.session import Session as SessionEntity

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
from ..schemas.session import (
    Session,
    SessionCreate,
    SessionList,
    SessionUpdate,
)

_COLLECTION = "sessions"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("session")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=Session)
    def create(
        user: str,
        body: SessionCreate,
        principal: Principal = Depends(get_principal),
        repo: SessionRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(SessionEntity(**payload)),
            Session,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{session}", response_model=Session)
    def get(
        user: str, session: str, repo: SessionRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, session, repo),
            Session,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{session}", response_model=Session)
    def patch(
        user: str,
        session: str,
        body: SessionUpdate,
        principal: Principal = Depends(get_principal),
        repo: SessionRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, session, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            Session,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{session}", status_code=204)
    def delete(
        user: str, session: str, repo: SessionRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, session, repo)
        repo.archive(session)
        return None

    @router.post("/{session}:undelete", response_model=Session)
    def undelete(
        user: str, session: str, repo: SessionRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, session, repo)
        repo.unarchive(session)
        return serialize_one(
            entity,
            Session,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{session}:purge", status_code=204)
    def purge(
        user: str, session: str, repo: SessionRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, session, repo)
        repo.delete(session)
        return None

    @router.get("", response_model=SessionList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: SessionRepository = Depends(repo_dep),
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
        items = repo.get_for_owner_between(user, rng.start, rng.end)
        window, next_token = paginate(items, params)
        rows = serialize_many(
            window,
            Session,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"sessions": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
