"""Postgres base repository for all entities."""

from typing import Any, Generic, Sequence, Type, TypeVar
from uuid import uuid4

from sqlalchemy import ColumnElement, select, true
from sqlalchemy.orm import Session, sessionmaker

from ....application.repositories.base_crud_repository import BaseCrudRepository
from ....domain.exceptions.domain_exception import EntityNotFoundException
from ....domain.models.base_entity import BaseEntity
from ..model.pg_base_entity import PGBaseEntity

Entity = TypeVar("Entity", bound=BaseEntity)
Persistence = TypeVar("Persistence", bound=PGBaseEntity)


class PGBaseRepository(BaseCrudRepository, Generic[Entity, Persistence]):
    """Base Postgres repository for all entities.

    Operates against a single JSONB-shaped table plus a `{table}_archive`
    companion (same shape, its own persistence type sharing the
    `PGBaseEntity` mixin under a different `__tablename__`), mirroring the
    Mongo `{collection}_archive` pattern.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        entity_type: Type[Entity],
        persistence_type: Type[Persistence],
        archive_persistence_type: Type[Persistence],
    ) -> None:
        self.session_factory = session_factory
        self.entity_type = entity_type
        self.persistence_type = persistence_type
        self.archive_persistence_type = archive_persistence_type

    def _to_row(self, entity: Entity) -> Persistence:
        return self.persistence_type.from_domain(entity)

    def _from_row(self, row: Persistence) -> Entity:
        return row.to_domain(self.entity_type)

    def create(self, entity: Entity) -> Entity:
        if not entity.id:
            entity.id = str(uuid4())
        row = self._to_row(entity)
        with self.session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._from_row(row)

    def execute_query(self, query: ColumnElement[bool]) -> Sequence[Persistence]:
        with self.session_factory() as session:
            return (
                session.execute(select(self.persistence_type).where(query))
                .scalars()
                .all()
            )

    def get_by_id(self, entity_id: str) -> Entity | None:
        with self.session_factory() as session:
            row = session.get(self.persistence_type, entity_id)
            return self._from_row(row) if row is not None else None

    def get_by_query(self, query: ColumnElement[bool]) -> list[Entity]:
        return [self._from_row(row) for row in self.execute_query(query)]

    def list_all(self) -> list[Entity]:
        return self.get_by_query(true())

    def save(self, entity: Entity) -> Entity:
        if not entity.id:
            return self.create(entity)
        row = self._to_row(entity)
        with self.session_factory() as session:
            existing = session.get(self.persistence_type, entity.id)
            if existing is None:
                row.revision = 0
                session.add(row)
                session.commit()
                session.refresh(row)
                return self._from_row(row)
            existing.owner = row.owner
            existing.created_at = row.created_at
            existing.updated_at = row.updated_at
            existing.data = row.data
            existing.revision = (existing.revision or 0) + 1
            session.commit()
            session.refresh(existing)
            return self._from_row(existing)

    def delete(self, entity_id: str) -> Any | None:
        with self.session_factory() as session:
            row = session.get(self.persistence_type, entity_id)
            if row is None:
                return None
            session.delete(row)
            session.commit()
            return entity_id

    def archive(self, entity_id: str) -> None:
        """Copy the row into the `{table}_archive` companion table.

        Leaves the original row untouched; archiving is a copy, not a move.
        """
        with self.session_factory() as session:
            row = session.get(self.persistence_type, entity_id)
            if row is None:
                raise EntityNotFoundException(f"Entity {entity_id} not found")
            archived = self.archive_persistence_type(
                id=row.id,
                owner=row.owner,
                created_at=row.created_at,
                updated_at=row.updated_at,
                revision=row.revision,
                data=row.data,
            )
            session.merge(archived)
            session.commit()

    def unarchive(self, entity_id: str) -> None:
        """Delete the row from `{table}_archive` if present; no-op otherwise."""
        with self.session_factory() as session:
            row = session.get(self.archive_persistence_type, entity_id)
            if row is None:
                return
            session.delete(row)
            session.commit()
