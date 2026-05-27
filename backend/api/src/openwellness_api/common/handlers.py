"""Shared serialization / mutation helpers used by every resource router.

These helpers do the AIP boundary work — they're the difference between
``backend/core``'s epoch-float + ``id`` representation and ``backend/api``'s
RFC-3339 + ``name`` wire format. Resource files compose these directly so
that the full HTTP contract is visible per resource (no factories).
"""

from __future__ import annotations

import time
from typing import Any, NoReturn

from fastapi import HTTPException
from pydantic import BaseModel, TypeAdapter

from openwellness_core.domain.exceptions.domain_exception import (
    EntityNotFoundException,
)

from ..deps.principal import Principal
from .resource_name import format_name
from .timestamps import epoch_to_rfc3339


def _entity_to_dict(entity: Any) -> dict[str, Any]:
    """Best-effort conversion of a dataclass entity to a plain dict.

    Domain entities are stdlib dataclasses, so ``__dict__`` is a clean
    view. Persistence-layer pydantic models would land here as ``dict``s
    via ``model_dump``; we delegate to that path when present.
    """
    dump = getattr(entity, "model_dump", None)
    if callable(dump):
        return dump()  # type: ignore[no-any-return]
    return dict(entity.__dict__)


def _project_audit_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop core-only audit fields that aren't part of the wire shape.

    ``created_at`` / ``updated_at`` are emitted as RFC-3339 ``createTime``
    / ``updateTime`` instead. The tz-offset audit fields stay internal —
    they're domain bookkeeping, not part of the public AIP shape.
    """
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    payload.pop("created_at_tz_offset", None)
    payload.pop("updated_at_tz_offset", None)
    return payload


def serialize_one(
    entity: Any,
    schema: type[BaseModel],
    *,
    collection: str,
    parent: str | None = None,
) -> Any:
    """Serialize a single entity through a response schema.

    Computes the AIP ``name`` from ``entity.id`` + ``collection`` + an
    optional ``parent`` resource name, attaches ``createTime`` /
    ``updateTime`` strings, and runs the result through the response
    schema (which provides camelCase aliasing per AIP-140).
    """
    payload = _entity_to_dict(entity)
    # AIP-122: ``name`` is reserved for the resource path. Move any
    # domain-level ``name`` to ``display_name`` (wire: ``displayName``)
    # before overwriting so the human-readable label isn't lost.
    if "name" in payload:
        payload.setdefault("display_name", payload["name"])
    payload["name"] = format_name(
        collection=collection, id_=getattr(entity, "id"), parent=parent
    )
    if "created_at" in payload:
        payload["createTime"] = epoch_to_rfc3339(payload.get("created_at"))
    if "updated_at" in payload:
        payload["updateTime"] = epoch_to_rfc3339(payload.get("updated_at"))
    payload = _project_audit_fields(payload)
    return TypeAdapter(schema).dump_python(
        schema.model_validate(payload), mode="json", by_alias=True
    )


def serialize_many(
    entities: list[Any],
    schema: type[BaseModel],
    *,
    collection: str,
    parent: str | None = None,
) -> list[Any]:
    """List-form of :func:`serialize_one`."""
    return [
        serialize_one(e, schema, collection=collection, parent=parent)
        for e in entities
    ]


def apply_patch(
    entity: Any,
    body: BaseModel,
    *,
    principal: Principal | None = None,
) -> None:
    """Apply a Pydantic update body to a domain entity in place.

    AIP-134 + this project's chosen update-mask convention: only fields
    the client explicitly set are mutated (``exclude_unset=True``). If
    ``principal`` is given, ``entity.updated_by`` is stamped to the
    principal id. ``entity.updated_at`` is bumped to the current time.
    """
    for key, value in body.model_dump(exclude_unset=True).items():
        if hasattr(entity, key):
            setattr(entity, key, value)
    if hasattr(entity, "updated_at"):
        entity.updated_at = time.time()
    if principal is not None and hasattr(entity, "updated_by"):
        entity.updated_by = principal.id


def stamp_audit(
    payload: dict[str, Any],
    *,
    parent_id: str | None,
    parent_field: str = "owner",
    principal: Principal,
) -> dict[str, Any]:
    """Stamp owner/audit fields onto a create payload dict.

    ``parent_id`` is the path parameter (e.g. ``/users/{user}`` → the
    user id). It's injected as ``payload[parent_field]`` so the entity
    constructor sees ownership from the path, not the request body.
    """
    if parent_id is not None:
        payload[parent_field] = parent_id
    payload.setdefault("updated_by", principal.id)
    return payload


def check_parent(
    entity: Any,
    *,
    parent_id: str,
    parent_field: str = "owner",
    collection: str,
    parent: str,
) -> Any:
    """404 if ``entity`` doesn't belong to ``parent_id``.

    Per AIP convention the API never reveals "this exists but isn't
    yours" — that's an information leak. 404 is the right answer for
    both "missing" and "wrong parent".
    """
    if getattr(entity, parent_field, None) != parent_id:
        raise EntityNotFoundException(
            f"{collection}/{getattr(entity, 'id', '?')} not found "
            f"for {parent}/{parent_id}"
        )
    return entity


def not_found(collection: str, id_: str, *, parent: str | None = None) -> NoReturn:
    """Raise the project-canonical ``EntityNotFoundException``."""
    if parent:
        raise EntityNotFoundException(
            f"{collection}/{id_} not found for {parent}"
        )
    raise EntityNotFoundException(f"{collection}/{id_} not found")


def bad_request(message: str) -> HTTPException:
    """Construct a 400 with the AIP-193 envelope."""
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": message,
                "details": [],
            }
        },
    )
