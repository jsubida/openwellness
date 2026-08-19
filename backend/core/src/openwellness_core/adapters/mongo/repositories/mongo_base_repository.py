"""Mongo base repository for all entities."""

import traceback
from typing import Any, Generic, Type, TypeVar

from bson import ObjectId

from ....application.repositories.base_crud_repository import BaseCrudRepository
from ....domain.exceptions.domain_exception import EntityNotFoundException
from ....domain.models.base_entity import BaseEntity
from ...exceptions import AdapterException
from ...interfaces.collection_repository import CollectionRepository
from ...interfaces.results.delete_result import DeleteResult
from ..model.mongo_base_entity import MongoBaseEntity

Entity = TypeVar("Entity", bound=BaseEntity)
Persistence = TypeVar("Persistence", bound=MongoBaseEntity)


class MongoBaseRepository(BaseCrudRepository, Generic[Entity, Persistence]):
    """Base Mongo repository for all entities."""

    def __init__(
        self,
        repo: CollectionRepository,
        entity_type: Type[Entity],
        persistence_type: Type[Persistence],
    ) -> None:
        self.repo = repo
        self.entity_type = entity_type
        self.persistence_type = persistence_type

    @property
    def _collection_name(self) -> str:
        return self.persistence_type.collection

    def _to_doc(self, entity: Entity) -> dict:
        return self.persistence_type.from_domain(entity).model_dump(by_alias=True)

    def _from_doc(self, doc: dict) -> Entity:
        return self.persistence_type.model_validate(doc).to_domain(self.entity_type)

    def _stamp_actor(self, doc: dict, actor: str) -> dict:
        """Record ``actor`` in the document's audit field, where one exists.

        **Whether this stamps anything depends on the persistence class, and
        today it stamps nothing.** Only `MongoBaseOwnerEntity` declares
        `updated_by` (alias `updatedBy`), and no concrete Mongo persistence
        class derives from it — every `BaseOwnerEntity`-backed entity in the
        ported subset lives in Couchbase. So in practice the Mongo backend
        currently *accepts* the actor for interface parity rather than
        recording it, and that is stated here rather than left for a reader to
        infer from an unused parameter.

        The condition, rather than an unconditional assignment, is what keeps
        that honest in both directions: an unconditional stamp would inject an
        `updatedBy` key into `users`, `studies` and every other collection
        whose schema has no such field, while a hard-coded no-op would mean
        the first `BaseOwnerEntity`-backed Mongo collection silently loses its
        attribution. This way it is stamped by construction the moment a
        persistence class declares the field.
        """
        if "updated_by" in self.persistence_type.model_fields:
            doc["updatedBy"] = actor
        return doc

    def create(self, entity: Entity, *, actor: str) -> Entity:
        """Insert a new document, attributing the write to ``actor``.

        See :meth:`_stamp_actor` for what the Mongo backend does with the
        value: today, nothing — no concrete Mongo persistence class carries an
        audit field. The parameter is still required, because the port is the
        same port the Couchbase backend implements and a backend that could
        be called without naming an actor is the divergence this phase closes.
        """
        collection = self.repo[self._collection_name]
        result = collection.insert_one(self._stamp_actor(self._to_doc(entity), actor))
        entity.id = str(result.inserted_id)
        fetched = collection.find_one({"_id": result.inserted_id})
        if fetched is None:
            raise AdapterException(
                f"Failed to fetch the created entity with ID {result.inserted_id}"
            )
        return self._from_doc(fetched)

    def execute_query(self, query: dict) -> Any:
        collection = self.repo[self._collection_name]
        return collection.find(query)

    def get_by_id(self, entity_id: str) -> Entity | None:
        try:
            collection = self.repo[self._collection_name]
            result = collection.find_one({"_id": ObjectId(entity_id)})
            return None if not result else self._from_doc(result)
        except AttributeError as e:
            print(f"Attribute error: {e}")
            return None
        except Exception as e:
            print(traceback.format_exc())
            print(f"An error occurred: {e}")
            return None

    def get_by_query(self, query: dict) -> list[Entity]:
        return [self._from_doc(item) for item in self.execute_query(query)]

    def list_all(self) -> list[Entity]:
        return self.get_by_query({})

    def init_entity_valid_fields(self, data: dict) -> Entity:
        return self._from_doc(data)

    def save(self, entity: Entity, *, actor: str) -> Entity:
        """Update an existing document, attributing the write to ``actor``.

        Accepted and — today — not recorded, for the reason given on
        :meth:`_stamp_actor`. An entity with no id is a create, and the actor
        is forwarded rather than re-derived.
        """
        if not entity.id:
            return self.create(entity, actor=actor)
        collection = self.repo[self._collection_name]
        collection.update_one(
            {"_id": ObjectId(entity.id)},
            {"$set": self._stamp_actor(self._to_doc(entity), actor)},
        )
        return entity

    def delete(self, entity_id: str) -> DeleteResult:
        collection = self.repo[self._collection_name]
        return collection.delete_one({"_id": ObjectId(entity_id)})

    def archive(self, entity_id: str, *, actor: str) -> None:
        """Insert a copy of the entity into the `{collection}_archive` collection.

        Leaves the original document in place; archiving is a copy, not a move.
        Callers that want move semantics should call `delete(entity_id)` after
        `archive(entity_id)`.

        ``actor`` attributes the archive copy — the copy is a new document,
        and the entity it is built from names whoever last edited the
        original, not whoever archived it. Accepted and, today, not recorded:
        see :meth:`_stamp_actor`.
        """
        entity = self.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundException(f"Entity {entity_id} not found")
        archive_collection_name = f"{self._collection_name}_archive"
        self.repo[archive_collection_name].insert_one(
            self._stamp_actor(self._to_doc(entity), actor)
        )

    def unarchive(self, entity_id: str) -> None:
        """Drop archive copies of an entity from ``{collection}_archive``.

        Inverse of :meth:`archive`: deletes archive-collection rows that
        share the original ``_id``. The original collection's document is
        untouched. No-op when no archive row exists.
        """
        archive_collection_name = f"{self._collection_name}_archive"
        try:
            self.repo[archive_collection_name].delete_many(
                {"_id": ObjectId(entity_id)}
            )
        except Exception:  # pragma: no cover - defensive
            return
