"""Post resource — owner-scoped (users-parented)."""

from __future__ import annotations

from typing import Any

import arrow
from fastapi import APIRouter, Depends, Query

from openwellness_core.application.repositories import PostRepository
from openwellness_core.domain.models.post import Post as PostEntity

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
from ..schemas.post import (
    Post,
    PostCreate,
    PostList,
    PostUpdate,
)

_COLLECTION = "posts"
_PARENT = "users"


def _parent_name(user: str) -> str:
    return format_name(collection=_PARENT, id_=user)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/{_PARENT}/{{user}}/{_COLLECTION}", tags=[_COLLECTION]
    )
    repo_dep = container_dep("post")

    def _fetch(user: str, id_: str, repo: Any) -> Any:
        entity = repo.get_by_id(id_)
        if entity is None:
            not_found(_COLLECTION, id_, parent=_parent_name(user))
        return check_parent(
            entity, parent_id=user, collection=_COLLECTION, parent=_PARENT
        )

    @router.post("", status_code=201, response_model=Post)
    def create(
        user: str,
        body: PostCreate,
        principal: Principal = Depends(get_principal),
        repo: PostRepository = Depends(repo_dep),
    ) -> Any:
        payload = stamp_audit(
            body.model_dump(exclude_unset=False),
            parent_id=user,
            principal=principal,
        )
        return serialize_one(
            repo.create(PostEntity(**payload)),
            Post,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.get("/{post}", response_model=Post)
    def get(
        user: str, post: str, repo: PostRepository = Depends(repo_dep)
    ) -> Any:
        return serialize_one(
            _fetch(user, post, repo),
            Post,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.patch("/{post}", response_model=Post)
    def patch(
        user: str,
        post: str,
        body: PostUpdate,
        principal: Principal = Depends(get_principal),
        repo: PostRepository = Depends(repo_dep),
    ) -> Any:
        entity = _fetch(user, post, repo)
        apply_patch(entity, body, principal=principal)
        return serialize_one(
            repo.save(entity),
            Post,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.delete("/{post}", status_code=204)
    def delete(
        user: str, post: str, repo: PostRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, post, repo)
        repo.archive(post)
        return None

    @router.post("/{post}:undelete", response_model=Post)
    def undelete(
        user: str, post: str, repo: PostRepository = Depends(repo_dep)
    ) -> Any:
        entity = _fetch(user, post, repo)
        repo.unarchive(post)
        return serialize_one(
            entity,
            Post,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )

    @router.post("/{post}:purge", status_code=204)
    def purge(
        user: str, post: str, repo: PostRepository = Depends(repo_dep)
    ) -> None:
        _fetch(user, post, repo)
        repo.delete(post)
        return None

    @router.get("", response_model=PostList)
    def list_items(
        user: str,
        start_time: str | None = Query(default=None, alias="startTime"),
        end_time: str | None = Query(default=None, alias="endTime"),
        params: PageParams = Depends(page_params),
        repo: PostRepository = Depends(repo_dep),
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
            Post,
            collection=_COLLECTION,
            parent=_parent_name(user),
        )
        return {"posts": rows, "nextPageToken": next_token}

    _ = (create, get, patch, delete, undelete, purge, list_items)
    return router
