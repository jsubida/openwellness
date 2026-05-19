"""Couchbase repository for FitbitSleep."""

from typing import Generic

from arrow import Arrow

from ....application.repositories.fitbit_sleep_repository import (
    FitbitSleepRepository,
    SomeFitbitSleep,
)
from ....domain.models.fitbit_sleep import FitbitSleep
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_fitbit import CBFitbitSleep
from .cb_base_repository import CBBaseRepository


class CBFitbitSleepRepository(
    FitbitSleepRepository,
    CBBaseRepository[SomeFitbitSleep, CBFitbitSleep],
    Generic[SomeFitbitSleep],
):
    """Couchbase repository for the FitbitSleep entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeFitbitSleep] = FitbitSleep,
        persistence_type: type[CBFitbitSleep] = CBFitbitSleep,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def create_from(self, d: dict) -> SomeFitbitSleep:
        data = self._validate_sleep_key_value(d)
        fs = self.init_entity_valid_fields(data)
        return self.create(fs)

    def update_from(self, entity: SomeFitbitSleep, d: dict) -> SomeFitbitSleep:
        data = self._validate_sleep_key_value(d)
        return self.update_entity_valid_fields(entity, data)

    def _validate_sleep_key_value(self, d: dict) -> dict:
        new_d = d.copy()
        if "sleep" not in d:
            new_d["sleep"] = []
        elif not isinstance(d["sleep"], list) or not all(
            isinstance(item, str) for item in d["sleep"]
        ):
            new_d["sleep"] = [item for item in d["sleep"] if isinstance(item, str)]
        return new_d

    def get_for_owner(self, owner_id: str, arg: Arrow) -> SomeFitbitSleep | None:
        q = self._build_get_query(owner_id, arg)
        items = self.repo.get_by_query(q)
        if len(items) > 1:
            raise ValueError(
                f"{len(items)} FitbitSleep found for owner {owner_id} on date {arg}"
            )
        return self.init_entity_valid_fields(items[0]) if len(items) == 1 else None

    def get_for_owner_between(
        self, owner_id: str, start: Arrow, end: Arrow
    ) -> list[SomeFitbitSleep]:
        q = self._build_get_between_query(owner_id, start, end)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_get_between_query(self, owner_id: str, start: Arrow, end: Arrow) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBFitbitSleep.type}"
                AND owner = "{owner_id}"
                AND fitbitDate BETWEEN "{start.format('YYYY-MM-DD')}" AND "{end.format('YYYY-MM-DD')}"
            ORDER BY fitbitDate, createdAt DESC
        """

    def _build_get_query(self, owner_id: str, arg: Arrow) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBFitbitSleep.type}"
                AND owner = "{owner_id}"
                AND fitbitDate = "{arg.format('YYYY-MM-DD')}"
            ORDER BY fitbitDate, createdAt DESC
        """
