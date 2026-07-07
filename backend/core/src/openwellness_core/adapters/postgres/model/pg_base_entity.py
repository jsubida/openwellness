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
from typing import Any, Self, Type, TypeVar

from sqlalchemy import JSON, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

E = TypeVar("E")

_PROMOTED_COLUMNS: tuple[str, ...] = ("id", "owner", "created_at", "updated_at")


class Base(DeclarativeBase):
    """Shared declarative base for all Postgres persistence classes."""


def _serialize_entity(entity: Any) -> dict:
    if dataclasses.is_dataclass(entity) and not isinstance(entity, type):
        return dataclasses.asdict(entity)
    return dict(vars(entity))


def _coerce_datetime(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return value


class PGBaseEntity:
    """Shared JSONB-first column shape for all Postgres-backed entities."""

    id: Mapped[str] = mapped_column(primary_key=True)
    owner: Mapped[str | None] = mapped_column(index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(default=0)
    # SQLite (used by the unit test suite as a fake backing store) can't
    # compile the Postgres-only JSONB type, so it falls back to portable JSON.
    data: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))

    # Explicit signature (SQLAlchemy would otherwise generate one at runtime
    # only) so type checkers can see the constructor kwargs through the
    # `Persistence` TypeVar bound to this mixin, e.g. in
    # `PGBaseRepository.archive()`. Assigns instrumented attributes directly
    # rather than delegating to `super().__init__()`, since this mixin has no
    # declared base of its own — `DeclarativeBase` only enters the MRO once a
    # concrete subclass mixes this in (e.g. `class Foo(PGBaseEntity, Base)`).
    def __init__(
        self,
        *,
        id: str,
        owner: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        revision: int = 0,
        data: dict,
    ) -> None:
        self.id = id
        self.owner = owner
        self.created_at = created_at
        self.updated_at = updated_at
        self.revision = revision
        self.data = data

    @classmethod
    def from_domain(cls, entity: Any) -> Self:
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
