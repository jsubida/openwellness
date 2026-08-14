"""BaseCrudRepository interface."""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

Entity = TypeVar("Entity")
Query = TypeVar("Query")


class BaseCrudRepository(ABC, Generic[Entity, Query]):
    """Common CRUD operations for entity repositories."""

    @abstractmethod
    def create(self, entity: Entity, *, actor: str) -> Entity:
        """Create an entity.

        ``actor`` names the identity recorded on the written record as the one
        that performed the write. It is required and keyword-only: the caller
        knows who acted, and an object that has been round-tripped through
        storage only knows who acted *last*. Implementations must not
        substitute a default, a service name, or a value read back off
        ``entity``.

        Machine identities are built with
        :func:`openwellness_core.application.actors.system_actor` rather than
        spelled inline, so a bare service name cannot reappear as a literal.
        """

    @abstractmethod
    def execute_query(self, query: Query) -> Any:
        """Execute a query."""

    @abstractmethod
    def get_by_id(self, entity_id: str) -> Entity | None:
        """Get an entity by its ID."""

    @abstractmethod
    def get_by_query(self, query: Query) -> list[Entity]:
        """Get entities by a query."""

    @abstractmethod
    def list_all(self) -> list[Entity]:
        """List all entities of this repository's type."""

    @abstractmethod
    def save(self, entity: Entity, *, actor: str) -> Entity:
        """Save an entity.

        ``actor`` carries the same contract as :meth:`create`: required,
        keyword-only, supplied by the caller, never defaulted or derived from
        ``entity``. This is the method the original defect ran through — a
        coach's edit stamped with the scheduler's own name — so a default
        here would restore it exactly.
        """

    @abstractmethod
    def delete(self, entity_id: str) -> Any | None:
        """Delete an entity by its ID."""

    @abstractmethod
    def archive(self, entity_id: str, *, actor: str) -> None:
        """Archive an entity by its ID.

        Implementations copy the existing entity into an archive slot
        (collection or type-discriminator) before any retention/deletion logic.

        ``actor`` is required here too, and its absence would be the easiest
        one to argue for: archiving writes a *copy*, so it is tempting to read
        it as a move rather than a write. It is a write — a new record is
        created, it carries an audit field, and under a 6-year retention
        policy the archive copy is the record most likely to be read back
        years later. Whoever archived it is exactly what a reader will want.

        :meth:`delete` and :meth:`unarchive` deliberately keep their
        signatures: neither writes a record that carries an audit field, and
        widening them would be ceremony without meaning.
        """

    @abstractmethod
    def unarchive(self, entity_id: str) -> None:
        """Restore an archived entity by its ID.

        Inverse of :meth:`archive`: removes the archive-slot copy so the
        original document is the canonical record again. A no-op (not an
        error) when no archive copy exists.
        """
