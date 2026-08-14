"""Couchbase base repository for all entities."""

import logging
from typing import Any, Generic, Type, TypeVar

from ....application.repositories.base_crud_repository import BaseCrudRepository
from ....domain.exceptions.domain_exception import EntityNotFoundException
from ....domain.models.base_entity import BaseEntity
from ...exceptions import ChannelsInvariantError
from ...interfaces.entity_repository import EntityRepository
from ..model.cb_base_entity import CBBaseEntity
from ._query_helpers import bucket_ident

Entity = TypeVar("Entity", bound=BaseEntity)
Persistence = TypeVar("Persistence", bound=CBBaseEntity)

# Non-field shadow attribute holding the `channels` array the repository read
# a document with. It is the guard's comparison source, kept separate from the
# live `channels` field so a caller mutating that field does not also move the
# value it is checked against.
_LOADED_CHANNELS_ATTR = "_loaded_channels"


class _Unset:
    """Sentinel type for "this entity carries no loaded-channels snapshot".

    `None` cannot serve as the sentinel: it is a meaningful snapshot value
    (the document was read and genuinely had no `channels` array), and the
    guard's decision differs between that case and an unverifiable one.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<no channels snapshot>"


_UNSET = _Unset()


class CBBaseRepository(BaseCrudRepository, Generic[Entity, Persistence]):
    """Base Couchbase repository for all entities."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[Entity],
        persistence_type: Type[Persistence],
    ) -> None:
        self.repo = repo
        self.entity_type = entity_type
        self.persistence_type = persistence_type

    def _to_doc(self, entity: Entity, archived: bool = False) -> dict:
        return self.persistence_type.from_domain(entity, archived=archived).model_dump(
            by_alias=True
        )

    def _from_doc(self, doc: dict) -> Entity:
        entity = self.persistence_type.model_validate(doc).to_domain(
            self.entity_type
        )
        # Dataclass entities don't declare this attribute; set it the same way
        # `CBBaseEntity` stashes `_archived`. A *copy* of the list is stored,
        # never the list object itself — sharing it would let a later mutation
        # of `entity.channels` move the snapshot too, and the guard would end
        # up comparing a value against itself.
        loaded = entity.channels
        object.__setattr__(
            entity,
            _LOADED_CHANNELS_ATTR,
            list(loaded) if loaded is not None else None,
        )
        return entity

    def _loaded_channels_of(self, entity: Entity) -> list[str] | None | _Unset:
        """Return the loaded-channels snapshot, or `_UNSET` if there is none."""
        return getattr(entity, _LOADED_CHANNELS_ATTR, _UNSET)

    def _assert_channels_invariant(self, entity: Entity, doc: dict) -> None:
        """Refuse a write that would destroy an existing document's access.

        Sync Gateway derives read access from the document body, so clearing
        a previously non-empty `channels` array revokes the document for
        every subscriber except its owner — with no HTTP error and no signal
        on the affected devices. This is the choke point where that is
        stopped, and it runs before the driver is called so a rejected write
        cannot have partially applied.

        The decision table (`specs/004-write-correctness/design.md`):

        | prior `_rev` | snapshot        | outgoing        | outcome  |
        |--------------|-----------------|-----------------|----------|
        | empty        | any             | any             | allowed  |
        | non-empty    | non-empty       | non-empty       | allowed  |
        | non-empty    | non-empty       | `None` or `[]`  | rejected |
        | non-empty    | `None` or `[]`  | `None` or `[]`  | allowed  |
        | non-empty    | absent          | `None` or `[]`  | rejected |
        | non-empty    | absent          | non-empty       | allowed  |

        `None` and `[]` are treated identically on the outgoing side (D-12).
        The production sync function tests `if (doc.channels != null)`; an
        empty array passes that test but contributes nothing, so the combined
        channel set collapses to `[doc.owner]` either way. Rejecting only the
        null spelling would leave the same hole open under the other one — do
        not "simplify" this to a null check.

        The absent-snapshot row rejects deliberately (D-13, an extension
        beyond the literal requirement). The snapshot is stamped whenever an
        entity is built from a document, so its absence on an entity carrying
        a non-empty revision means a stored document exists whose channel set
        this process has never seen. D-10 forbids a read-before-write round
        trip to resolve it, and a "fail closed" that lets the unverifiable
        case through is not fail closed. A legitimate caller loads the entity
        through this repository first, which is the intended usage anyway.

        Raises:
            ChannelsInvariantError: with the document id, document type,
                prior channel set and attempted channel value.
        """
        if not getattr(entity, "_rev", ""):
            # No prior revision: this write creates the document, so there is
            # no existing access for it to destroy.
            return

        outgoing = doc.get("channels")
        if outgoing:
            # A non-empty array is being written. Access is being set or
            # intentionally changed, not removed — including the derived
            # routing channel `CBParticipantGroup.from_domain` stamps.
            return

        snapshot = self._loaded_channels_of(entity)
        if not isinstance(snapshot, _Unset) and not snapshot:
            # Read back with no channels, written back with no channels:
            # there was never any access to lose.
            return

        # An absent snapshot is reported as `None`; it cannot be confused
        # with a snapshot that *was* `None`, because that combination is the
        # allowed row above and never reaches here.
        prior = None if isinstance(snapshot, _Unset) else snapshot
        # Resolve identity defensively — a guard that raises `KeyError` while
        # reporting a violation is worse than the violation.
        doc_id = doc.get("id") or getattr(entity, "id", "")
        doc_type = doc.get("type") or self.persistence_type.type
        # Keep this message prefix stable: a log-based alert rule is the
        # intended operational follow-up, and a rewording silently breaks it.
        logging.error(
            "Channels invariant violated for %s (type=%s); prior channels=%s;"
            " attempted channels=%s",
            doc_id,
            doc_type,
            prior,
            outgoing,
        )
        raise ChannelsInvariantError(
            doc_id=doc_id,
            doc_type=doc_type,
            prior_channels=prior,
            outgoing_channels=outgoing,
        )

    def create(self, entity: Entity, *, actor: str) -> Entity:
        """Store a new document, recording ``actor`` as the writing identity.

        The value is passed straight to the driver, which stamps it onto the
        document body. It is never read off ``entity``: 08-06's interim
        entity-derived bridge is deleted, because an entity that came back
        from storage only knows who wrote it last, not who is writing it now.
        """
        result = self.repo.create(self._to_doc(entity), actor=actor)
        return self._from_doc(result)

    def execute_query(self, query: str, params: dict | None = None) -> Any:
        """Execute a N1QL query and return raw dict rows.

        All user-supplied values must be passed via ``params`` (named
        parameters: ``$name`` in ``query``). Only the bucket name and
        allowlisted column identifiers may be interpolated into ``query``.
        """
        return self.repo.get_by_query(query, params)

    def get_by_id(self, entity_id: str) -> Entity | None:
        result = self.repo.get_by_id(entity_id)
        return self._from_doc(result) if result else None

    def get_by_query(
        self, query: str, params: dict | None = None
    ) -> list[Entity]:
        """Execute a N1QL query and rehydrate domain entities from the rows.

        See :meth:`execute_query` for the parameterization contract.
        """
        return [
            self._from_doc(item) for item in self.execute_query(query, params)
        ]

    def list_all(self) -> list[Entity]:
        b = bucket_ident(self.repo.bucket)
        q = f"SELECT b.* FROM {b} AS b WHERE b.type = $type"
        return self.get_by_query(q, {"type": self.persistence_type.type})

    def init_entity_valid_fields(self, data: dict) -> Entity:
        """Create an entity from a wire-format dict (e.g., raw N1QL rows)."""
        return self._from_doc(data)

    def update_entity_valid_fields(self, entity: Entity, data: dict) -> Entity:
        """Apply a wire-format dict's fields onto an existing entity in place."""
        valid = self.entity_type.valid_fields()
        rehydrated = self.persistence_type.model_validate(data).model_dump(
            by_alias=False
        )
        if "rev" in rehydrated:
            rehydrated["_rev"] = rehydrated.pop("rev")
        for key, value in rehydrated.items():
            if key in valid:
                setattr(entity, key, value)
        # This is the second entry point that loads stored state onto an
        # entity, so it re-stamps the snapshot too; leaving it out would make
        # a freshly refreshed entity look unverifiable to the write guard.
        loaded = rehydrated.get("channels")
        object.__setattr__(
            entity,
            _LOADED_CHANNELS_ATTR,
            list(loaded) if loaded is not None else None,
        )
        return entity

    def save(self, entity: Entity, *, actor: str) -> Entity:
        """Update the stored document for an existing entity.

        ``actor`` names the identity recorded on the document as the writer;
        the driver stamps it. Supplied by the caller, never derived from
        ``entity`` — this is the path the original misattribution ran through.

        Enforces the channels invariant before anything leaves the process:
        a write that would clear a previously non-empty `channels` array
        raises :class:`ChannelsInvariantError` and is never sent to the
        driver. See :meth:`_assert_channels_invariant`. The guard runs before
        the driver call, so a rejected write also stamps nothing.
        """
        doc = self._to_doc(entity)
        self._assert_channels_invariant(entity, doc)
        result = self.repo.save(doc, actor=actor)
        return self._from_doc(result)

    def delete(self, entity_id: str) -> None:
        self.repo.delete(entity_id)

    def archive(self, entity_id: str, *, actor: str) -> None:
        """Create an archive copy of an entity, leaving the original in place.

        ``actor`` is stamped onto the archive copy. It cannot be skipped on
        the grounds that this method re-reads the entity rather than accepting
        one: the copy is a new document with its own audit field, and the
        entity it is built from carries whoever last touched the *original*,
        which is not who is archiving it now.

        Deliberately unguarded by :meth:`_assert_channels_invariant`, and the
        absence is a decision rather than an oversight (D-09). This POSTs a
        *different* document — type `<Entity>Archived`, per
        :meth:`CBBaseEntity.from_domain` — which has no prior revision and
        therefore no existing access to destroy. Running the guard here would
        reject legitimate archives of channel-bearing entities. The guard
        belongs on the update/upsert path, which is :meth:`save`.
        """
        entity = self.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundException(f"Entity {entity_id} not found")
        self.repo.create(self._to_doc(entity, archived=True), actor=actor)

    def unarchive(self, entity_id: str) -> None:
        """Drop the archive copy of an entity, if one exists.

        In the Couchbase representation, archiving stores a *new* document
        with ``type = "<EntityType>Archived"`` (see
        :meth:`CBBaseEntity.from_domain`). The original document keeps its
        live ``type``. Unarchive deletes the archived document so a future
        ``archive(...)`` call won't conflict; the original is untouched.
        """
        b = bucket_ident(self.repo.bucket)
        archived_type = f"{self.persistence_type.type}Archived"
        q = (
            f"SELECT META(b).id AS doc_id FROM {b} AS b "
            f"WHERE b.id = $entity_id AND b.type = $archived_type"
        )
        rows = self.repo.get_by_query(
            q, {"entity_id": entity_id, "archived_type": archived_type}
        )
        for row in rows:
            self.repo.delete(row["doc_id"])
