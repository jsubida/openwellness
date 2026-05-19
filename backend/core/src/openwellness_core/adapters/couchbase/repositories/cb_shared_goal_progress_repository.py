"""Couchbase repository for SharedGoalProgress."""

from ....application.repositories.shared_goal_progress_repository import (
    SharedGoalProgressRepository,
    SomeSharedGoalProgress,
)
from ....domain.models.shared_goal_progress import SharedGoalProgress
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_shared_goal_progress import CBSharedGoalProgress
from .cb_base_repository import CBBaseRepository


class CBSharedGoalProgressRepository(
    SharedGoalProgressRepository,
    CBBaseRepository[SomeSharedGoalProgress, CBSharedGoalProgress],
):
    """Couchbase repository for the SharedGoalProgress entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeSharedGoalProgress] = SharedGoalProgress,
        persistence_type: type[CBSharedGoalProgress] = CBSharedGoalProgress,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def create_using(
        self, date: str, channels: list[str], owner: str, study_id: str
    ) -> SomeSharedGoalProgress:
        # Channels are persistence-layer routing — domain entity doesn't carry them.
        # Caller can supply via the persistence class if a custom channel set is needed;
        # otherwise the default CBBaseEntity.channels is left None.
        return self.entity_type(date=date, owner=owner, study_id=study_id)

    def get_for_owner(self, owner_id: str, arg: str) -> SomeSharedGoalProgress | None:
        q = self._generate_query(owner_id, arg, arg)
        items = self.repo.get_by_query(q)
        if len(items) == 0:
            return None
        return self.init_entity_valid_fields(items[-1])

    def get_for_owner_between(
        self, owner_id: str, start: str, end: str
    ) -> list[SomeSharedGoalProgress]:
        q = self._generate_query(owner_id, start, end)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _generate_query(self, owner_id: str, start: str, end: str) -> str:
        b = self.repo.bucket
        return f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type="{CBSharedGoalProgress.type}"
                AND owner='{owner_id}'
                AND date BETWEEN '{start}' AND '{end}'
            ORDER BY date, createdAt;
        """
