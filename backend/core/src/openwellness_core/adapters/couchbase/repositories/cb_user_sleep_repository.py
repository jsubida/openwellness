"""Couchbase repository for UserSleep."""

from typing import List, Type, TypeVar

from ....application.repositories.user_sleep_repository import UserSleepRepository
from ....domain.models.user_sleep import UserSleep
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_user import CBUserSleep
from .cb_base_repository import CBBaseRepository

SomeUserSleep = TypeVar("SomeUserSleep", bound=UserSleep)


class CBUserSleepRepository(
    UserSleepRepository[SomeUserSleep], CBBaseRepository[SomeUserSleep, CBUserSleep]
):
    """Couchbase repository for the UserSleep entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeUserSleep] = UserSleep,
        persistence_type: type[CBUserSleep] = CBUserSleep,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_user_sleeps_in_range(
        self, owner: str, start: str, end: str
    ) -> List[SomeUserSleep]:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type="{CBUserSleep.type}"
            AND owner="{owner}"
            AND sleepDate BETWEEN '{start}' AND '{end}'
            ORDER BY sleepDate, createdAt
        """
        return self.get_by_query(q)

    def get_user_sleeps_for_date(self, owner: str, date: str) -> List[SomeUserSleep]:
        return self.get_user_sleeps_in_range(owner, date, date)
