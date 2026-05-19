"""Couchbase repository for DailyState."""

from arrow import Arrow

from ....application.repositories.daily_state_repository import (
    DailyStateRepository,
    SomeDailyState,
)
from ....domain.models.daily_state import DailyState
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_daily_state import CBDailyState
from .cb_base_repository import CBBaseRepository


class CBDailyStateRepository(
    DailyStateRepository, CBBaseRepository[SomeDailyState, CBDailyState]
):
    """Couchbase repository for the DailyState entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeDailyState] = DailyState,
        persistence_type: type[CBDailyState] = CBDailyState,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_owner(self, owner_id: str, arg: Arrow) -> SomeDailyState | None:
        items = self.get_for_owner_between(owner_id, arg, arg)
        return items[0] if len(items) == 1 else None

    def get_for_owner_between(
        self, owner_id: str, start: Arrow, end: Arrow
    ) -> list[SomeDailyState]:
        q = self._build_get_between_query(owner_id, start, end)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_get_between_query(self, owner_id: str, start: Arrow, end: Arrow) -> str:
        ymd = "YYYY-MM-DD"
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBDailyState.type}"
                AND owner = "{owner_id}"
                AND date BETWEEN "{start.format(ymd)}" AND "{end.format(ymd)}"
            ORDER BY date, createdAt
        """
