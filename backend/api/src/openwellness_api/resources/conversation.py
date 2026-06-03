"""Conversation resource — top-level with AIP-136 ``:search`` method."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from openwellness_core.application.repositories import ConversationRepository
from openwellness_core.domain.models.conversation import Conversation as ConversationEntity

from ..common.handlers import (
    apply_patch,
    not_found,
    serialize_many,
    serialize_one,
)
from ..common.pagination import PageParams, page_params, paginate
from ..deps.container import container_dep
from ..deps.principal import Principal, get_principal
from ..schemas.conversation import (
    Conversation,
    ConversationCreate,
    ConversationList,
    ConversationSearchBody,
    ConversationUpdate,
)

_COLLECTION = "conversations"


def build_router() -> APIRouter:
    router = APIRouter(prefix=f"/{_COLLECTION}", tags=[_COLLECTION])
    repo_dep = container_dep("conversation")

    def _fetch(id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_)
        return entity

    @router.post("", status_code=201, response_model=Conversation)
    def create(
        body: ConversationCreate,
        principal: Principal = Depends(get_principal),
        repo: ConversationRepository = Depends(repo_dep),
    ) -> Any:
        entity = ConversationEntity(**body.model_dump(exclude_unset=False))
        return serialize_one(repo.create(entity), Conversation, collection=_COLLECTION)

    @router.get("/{conversation}", response_model=Conversation)
    def get(
        conversation: str, repo: ConversationRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(conversation, repo), Conversation, collection=_COLLECTION
        )

    @router.patch("/{conversation}", response_model=Conversation)
    def patch(
        conversation: str,
        body: ConversationUpdate,
        principal: Principal = Depends(get_principal),
        repo: ConversationRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(conversation, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity), Conversation, collection=_COLLECTION
        )

    @router.delete("/{conversation}", status_code=204)
    def delete(
        conversation: str, repo: ConversationRepository = Depends(repo_dep)
    ) -> None:
        _fetch(conversation, repo)
        repo.archive(conversation)
        return None

    @router.post("/{conversation}:undelete", response_model=Conversation)
    def undelete(
        conversation: str, repo: ConversationRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(conversation, repo)
        repo.unarchive(conversation)
        return serialize_one(entity, Conversation, collection=_COLLECTION)

    @router.post("/{conversation}:purge", status_code=204)
    def purge(
        conversation: str, repo: ConversationRepository = Depends(repo_dep)
    ) -> None:
        _fetch(conversation, repo)
        repo.delete(conversation)
        return None

    @router.get("", response_model=ConversationList)
    def list_items(
        params: PageParams = Depends(page_params),
        repo: ConversationRepository = Depends(repo_dep),
    ) -> Any:
        items = repo.list_all()
        window, next_token = paginate(items, params)
        rows = serialize_many(window, Conversation, collection=_COLLECTION)
        return {"conversations": rows, "nextPageToken": next_token}

    @router.post(":search", response_model=ConversationList)
    def search(
        body: ConversationSearchBody,
        params: PageParams = Depends(page_params),
        repo: ConversationRepository = Depends(repo_dep),
    ) -> Any:
        type_map = {
            "channels": ConversationEntity.Filter.Type.CHANNELS,
            "kind": ConversationEntity.Filter.Type.KIND,
            "week": ConversationEntity.Filter.Type.WEEK,
        }
        filters = [
            ConversationEntity.Filter(type=type_map[f.type], val=f.val)
            for f in body.filters
        ]
        results = repo.get_for_filters(filters)
        window, next_token = paginate(results, params)
        rows = serialize_many(window, Conversation, collection=_COLLECTION)
        return {"conversations": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items, search)
    return router
