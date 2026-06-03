"""Card resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import CardRepository
from openwellness_core.domain.models.card import Card as CardEntity

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
from ..schemas.card import (
    Card,
    CardCreate,
    CardList,
    CardUpdate,
)

_COLLECTION = "cards"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("card")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=Card)
    def create(
        user: str,
        body: CardCreate,
        principal: Principal = Depends(get_principal),
        repo: CardRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(CardEntity(**payload)),
            Card,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{card}", response_model=Card)
    def get(
        user: str, card: str, repo: CardRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, card, repo),
            Card,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{card}", response_model=Card)
    def patch(
        user: str,
        card: str,
        body: CardUpdate,
        principal: Principal = Depends(get_principal),
        repo: CardRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, card, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            Card,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{card}", status_code=204)
    def delete(
        user: str, card: str, repo: CardRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, card, repo)
        repo.archive(card)
        return None

    @router.post("/{card}:undelete", response_model=Card)
    def undelete(
        user: str, card: str, repo: CardRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, card, repo)
        repo.unarchive(card)
        return serialize_one(
            entity,
            Card,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{card}:purge", status_code=204)
    def purge(
        user: str, card: str, repo: CardRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, card, repo)
        repo.delete(card)
        return None

    @router.get("", response_model=CardList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: CardRepository = Depends(repo_dep),
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
            Card,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"cards": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
