"""Couchbase repository for FitbitWeight."""

from typing import Type

from ....application.repositories.fitbit_weight_repository import (
    FitbitWeightRepository,
    SomeFitbitWeight,
)
from ....domain.models.fitbit_weight import FitbitWeight
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_fitbit import CBFitbitWeight
from .cb_base_repository import CBBaseRepository


class CBFitbitWeightRepository(
    FitbitWeightRepository, CBBaseRepository[SomeFitbitWeight, CBFitbitWeight]
):
    """Couchbase repository for the FitbitWeight entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeFitbitWeight] = FitbitWeight,
        persistence_type: type[CBFitbitWeight] = CBFitbitWeight,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)

    def get_for_owner(self, owner: str, date: str) -> list[SomeFitbitWeight]:
        return self.get_for_owner_between(owner, date, date)

    def get_for_owner_between(
        self, owner: str, start: str, end: str
    ) -> list[SomeFitbitWeight]:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBFitbitWeight.type}"
                AND owner = "{owner}"
                AND fitbitDate BETWEEN "{start}" AND "{end}"
                ORDER BY createdAt ASC
        """
        return [
            self.init_entity_valid_fields(item) for item in self.repo.get_by_query(q)
        ]
