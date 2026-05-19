"""Couchbase repository for Conditions."""

from ....application.repositories.condition_repository import (
    ConditionRepository,
    SomeCondition,
)
from ....domain.models.condition import Condition
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_condition import CBCondition
from .cb_base_repository import CBBaseRepository


class CBConditionRepository(
    ConditionRepository, CBBaseRepository[SomeCondition, CBCondition]
):
    """Couchbase repository for the Condition entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeCondition] = Condition,
        persistence_type: type[CBCondition] = CBCondition,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_owner(self, owner_id: str, arg: int) -> SomeCondition | None:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBCondition.type}"
                AND owner = "{owner_id}"
                AND week = {arg}
            ORDER BY week, createdAt DESC
        """
        items = self.repo.get_by_query(q)
        if len(items) == 1:
            return self.init_entity_valid_fields(items[0])
        elif len(items) > 1:
            raise ValueError(
                f"Multiple Conditions found for owner {owner_id} on week {arg}"
            )
        return None

    def get_for_owner_between(
        self, owner_id: str, start: int, end: int
    ) -> list[SomeCondition]:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBCondition.type}"
                AND owner = "{owner_id}"
                AND week BETWEEN {start} AND {end}
            ORDER BY week, createdAt DESC
        """
        return self.get_by_query(q)
