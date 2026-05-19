"""Couchbase repository for FitbitSleepSession."""

from typing import Generic

from arrow import Arrow

from ....application.repositories.fitbit_sleep_session_repository import (
    FitbitSleepSessionRepository,
    SomeFitbitSleepSession,
)
from ....domain.models.fitbit_sleep_session import FitbitSleepSession
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_fitbit import CBFitbitSleepSession
from .cb_base_repository import CBBaseRepository


class CBFitbitSleepSessionRepository(
    FitbitSleepSessionRepository,
    CBBaseRepository[SomeFitbitSleepSession, CBFitbitSleepSession],
    Generic[SomeFitbitSleepSession],
):
    """Couchbase repository for the FitbitSleepSession entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeFitbitSleepSession] = FitbitSleepSession,
        persistence_type: type[CBFitbitSleepSession] = CBFitbitSleepSession,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def create_from(self, d: dict) -> SomeFitbitSleepSession:
        return self.init_entity_valid_fields(d)

    def update_from(
        self, entity: SomeFitbitSleepSession, d: dict
    ) -> SomeFitbitSleepSession:
        return self.update_entity_valid_fields(entity, d)

    def get_for_owner(self, owner_id: str, arg: Arrow) -> SomeFitbitSleepSession | None:
        q = self._build_get_query(owner_id, arg)
        items = self.repo.get_by_query(q)
        if len(items) > 1:
            raise ValueError(
                f"{len(items)} FitbitSleepSessions found for owner {owner_id} on date {arg}"
            )
        return self.init_entity_valid_fields(items[0]) if len(items) == 1 else None

    def get_for_owner_between(
        self, owner_id: str, start: Arrow, end: Arrow
    ) -> list[SomeFitbitSleepSession]:
        q = self._build_get_between_query(owner_id, start, end)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_get_between_query(self, owner_id: str, start: Arrow, end: Arrow) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBFitbitSleepSession.type}"
                AND owner = "{owner_id}"
                AND fitbitDate BETWEEN "{start.format('YYYY-MM-DD')}" AND "{end.format('YYYY-MM-DD')}"
            ORDER BY fitbitDate, createdAt DESC
        """

    def _build_get_query(self, owner_id: str, arg: Arrow) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBFitbitSleepSession.type}"
                AND owner = "{owner_id}"
                AND fitbitDate = "{arg.format('YYYY-MM-DD')}"
            ORDER BY fitbitDate, createdAt DESC
        """
