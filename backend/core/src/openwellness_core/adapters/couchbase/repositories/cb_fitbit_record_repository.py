"""Couchbase repository for FitbitRecord."""

from typing import Type

from ....application.dtos.activity_data_dto import ActivityDataInputDTO
from ....application.repositories.fitbit_record_repository import FitbitRecordRepository
from ....domain.models.fitbit_record import FitbitRecord
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_fitbit import CBFitbitRecord
from .cb_base_repository import CBBaseRepository


class CBFitbitRecordRepository(
    FitbitRecordRepository, CBBaseRepository[FitbitRecord, CBFitbitRecord]
):
    """Couchbase repository for the FitbitRecord entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[FitbitRecord] = FitbitRecord,
        persistence_type: type[CBFitbitRecord] = CBFitbitRecord,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def create_from_notification(
        self,
        pid: str,
        fitbit_date: str,
        study_id: str,
        data: ActivityDataInputDTO,
    ) -> FitbitRecord:
        record = self.entity_type(
            owner=pid,
            study_id=study_id,
            fitbit_date=fitbit_date,
            active_score=data.active_score,
            activity_calories=data.activity_calories,
            calories_bmr=data.calories_bmr,
            calories_out=data.calories_out,
            distances=data.distances,
            fairly_active_minutes=data.fairly_active_minutes,
            lightly_active_minutes=data.lightly_active_minutes,
            marginal_calories=data.marginal_calories,
            sedentary_minutes=data.sedentary_minutes,
            steps=data.steps,
            very_active_minutes=data.very_active_minutes,
        )
        return self.create(record)

    def get_for_owner(self, owner_id: str, arg: str) -> FitbitRecord | None:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBFitbitRecord.type}"
                AND owner = "{owner_id}"
                AND fitbitDate = "{arg}"
        """
        items = self.repo.get_by_query(q)
        if len(items) == 1:
            return self.init_entity_valid_fields(items[0])
        elif len(items) > 1:
            raise ValueError(
                f"Multiple FitbitRecords found for owner {owner_id} on date {arg}"
            )
        return None

    def get_for_owner_between(
        self, owner_id: str, start: str, end: str
    ) -> list[FitbitRecord]:
        q = self._generate_query(owner_id, start, end)
        return [
            self.init_entity_valid_fields(item) for item in self.repo.get_by_query(q)
        ]

    def _generate_query(self, owner: str, start: str, end: str) -> str:
        b = self.repo.bucket
        return f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBFitbitRecord.type}"
                AND fitbitDate BETWEEN "{start}" AND "{end}"
                AND owner = "{owner}"
            ORDER BY fitbitDate,
                    createdAt DESC
        """
