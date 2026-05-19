"""Couchbase repository for UserFood."""

from typing import List, Type

from arrow import Arrow

from ....application.repositories.user_food_repository import (
    SomeUserFood,
    UserFoodRepository,
)
from ....domain.models.user_food import UserFood
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_user import CBUserFood
from .cb_base_repository import CBBaseRepository


class CBUserFoodRepository(
    UserFoodRepository[SomeUserFood], CBBaseRepository[SomeUserFood, CBUserFood]
):
    """Couchbase repository for the UserFood entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeUserFood] = UserFood,
        persistence_type: type[CBUserFood] = CBUserFood,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_owner(self, owner: str, arg: Arrow) -> SomeUserFood | None:
        raise NotImplementedError("This method should not be used directly.")

    def get_for_owner_between(
        self, owner: str, start: Arrow, end: Arrow
    ) -> List[SomeUserFood]:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type="{CBUserFood.type}"
            AND owner="{owner}"
            AND eatenAt BETWEEN {start.timestamp()} AND {end.timestamp()}
            ORDER BY eatenAt, createdAt
        """
        return self.get_by_query(q)

    def get_for_owner_on_day(self, owner: str, arg: Arrow) -> List[SomeUserFood]:
        start = arg.floor("day")
        end = arg.ceil("day")
        return self.get_for_owner_between(owner, start, end)
