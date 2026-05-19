"""Couchbase repository for UserStress."""

from typing import List, Type, TypeVar

from ....application.repositories.user_stress_repository import UserStressRepository
from ....domain.models.user_stress import UserStress
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_user import CBUserStress
from .cb_base_repository import CBBaseRepository

SomeUserStress = TypeVar("SomeUserStress", bound=UserStress)


class CBUserStressRepository(
    UserStressRepository[SomeUserStress],
    CBBaseRepository[SomeUserStress, CBUserStress],
):
    """Couchbase repository for the UserStress entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeUserStress] = UserStress,
        persistence_type: type[CBUserStress] = CBUserStress,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_user_stresses_in_range(
        self, owner: str, start: str, end: str
    ) -> List[SomeUserStress]:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type="{CBUserStress.type}"
            AND owner="{owner}"
            AND stressDate BETWEEN '{start}' AND '{end}'
            ORDER BY stressDate, createdAt
        """
        return self.get_by_query(q)

    def get_user_stresses_for_date(
        self, owner: str, date: str
    ) -> List[SomeUserStress]:
        return self.get_user_stresses_in_range(owner, date, date)
