"""Postgres persistence base for all entities.

Unlike the Mongo/Couchbase persistence bases (pydantic DTOs), this is a
SQLAlchemy declarative mixin: SQLAlchemy ORM classes are the idiomatic
Postgres persistence representation, and Alembic migrates their table shape
directly. The `data` JSONB column is the source of truth for the full
entity — `id`/`owner`/`created_at`/`updated_at` are promoted columns kept in
sync for indexed/range queries (e.g. `owner` + `created_at BETWEEN`), not an
independent representation.
"""

import dataclasses
from datetime import datetime, timezone
from typing import Any, Type, TypeVar

from sqlalchemy import JSON, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, declarative_mixin

E = TypeVar("E")

Base = declarative_base()

_PROMOTED_COLUMNS: tuple[str, ...] = ("id", "owner", "created_at", "updated_at")


def _serialize_entity(entity: Any) -> dict:
    return dataclasses.asdict(entity) if dataclasses.is_dataclass(entity) else vars(entity)


def _coerce_datetime(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return value


@declarative_mixin
class PGBaseEntity:
    """Shared JSONB-first column shape for all Postgres-backed entities."""

    # Plain (unannotated) `Column` assignments, matching the other two
    # backends' persistence bases — annotating these would make SQLAlchemy
    # 2.0 treat them as `Mapped[]`-style declarations, which plain `Column`
    # values aren't.
    id = Column(String, primary_key=True)
    owner = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    revision = Column(Integer, nullable=False, default=0)
    # SQLite (used by the unit test suite as a fake backing store) can't
    # compile the Postgres-only JSONB type, so it falls back to portable JSON.
    data = Column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)

    @classmethod
    def from_domain(cls, entity: Any) -> "PGBaseEntity":
        kwargs: dict[str, Any] = {"data": _serialize_entity(entity)}
        for name in _PROMOTED_COLUMNS:
            if not hasattr(entity, name):
                continue
            value = getattr(entity, name)
            if name in ("created_at", "updated_at"):
                value = _coerce_datetime(value)
            kwargs[name] = value
        return cls(**kwargs)

    def to_domain(self, entity_cls: Type[E]) -> E:
        return entity_cls(**self.data)
