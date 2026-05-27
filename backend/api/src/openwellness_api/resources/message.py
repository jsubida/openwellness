"""Message resource — owner-scoped, ``filter=`` supports ``subtype`` and ``condition``."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import MessageRepository
from openwellness_core.domain.models.message import Message as MessageEntity

from ..common.filter import parse_filter
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
from ..schemas.message import Message, MessageCreate, MessageList, MessageUpdate

_COLLECTION = "messages"
_PARENT = "users"
_FILTERABLE = {"subtype": int, "condition": int}


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("message")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=Message)
    def create(
        user: str,
        body: MessageCreate,
        principal: Principal = Depends(get_principal),
        repo: MessageRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(MessageEntity(**payload)),
            Message,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{message}", response_model=Message)
    def get(
        user: str, message: str, repo: MessageRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, message, repo),
            Message,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{message}", response_model=Message)
    def patch(
        user: str,
        message: str,
        body: MessageUpdate,
        principal: Principal = Depends(get_principal),
        repo: MessageRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, message, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            Message,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{message}", status_code=204)
    def delete(
        user: str, message: str, repo: MessageRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, message, repo)
        repo.archive(message)
        return None

    @router.post("/{message}:undelete", response_model=Message)
    def undelete(
        user: str, message: str, repo: MessageRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, message, repo)
        repo.unarchive(message)
        return serialize_one(
            entity, Message, collection=_COLLECTION, parent=_parent_name(user)
        )

    @router.post("/{message}:purge", status_code=204)
    def purge(
        user: str, message: str, repo: MessageRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, message, repo)
        repo.delete(message)
        return None

    @router.get("", response_model=MessageList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        filter: str | None = Query(default=None),  # AIP-160
        params: PageParams = Depends(page_params),
        repo: MessageRepository = Depends(repo_dep),
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
        parsed = parse_filter(filter, allowed_fields=_FILTERABLE)
        results = repo.get_for_owner_between(
            user,
            rng.start,
            rng.end,
            subtype=parsed.get("subtype"),
            condition=parsed.get("condition"),
        )
        window, next_token = paginate(results, params)
        rows = serialize_many(
            window, Message, collection=_COLLECTION, parent=_parent_name(user)
        )
        return {"messages": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
