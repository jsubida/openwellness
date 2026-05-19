"""Couchbase repository for ActigraphRecord."""

from typing import Type

from arrow import Arrow

from ....application.repositories.actigraph_record_repository import (
    ActigraphRecordRepository,
)
from ....domain.models.actigraph_record import ActigraphRecord
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_actigraph_record import CBActigraphRecord
from .cb_base_repository import CBBaseRepository


class CBActigraphRecordRepository(
    ActigraphRecordRepository,
    CBBaseRepository[ActigraphRecord, CBActigraphRecord],
):
    """Couchbase repository for the ActigraphRecord entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[ActigraphRecord] = ActigraphRecord,
        persistence_type: type[CBActigraphRecord] = CBActigraphRecord,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_owner(self, owner_id: str, arg: Arrow) -> ActigraphRecord | None:
        raise RuntimeError("DO NOT USE")

    def get_for_owner_between(
        self, owner_id: str, start: Arrow, end: Arrow
    ) -> list[ActigraphRecord]:
        s = start.format("YYYY-MM-DD")
        e = end.format("YYYY-MM-DD")
        q = self._generate_query(owner_id, s, e)
        return [
            self.init_entity_valid_fields(item) for item in self.repo.get_by_query(q)
        ]

    def _generate_query(self, owner: str, start: str, end: str) -> str:
        b = self.repo.bucket
        return f"""
        SELECT records.*
        FROM (
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBActigraphRecord.type}"
                AND timestampUTC BETWEEN "{start}" AND "{end}"
                AND owner = "{owner}"
            ORDER BY timestampUTC,
                    createdAt DESC
        ) AS records
        INNER JOIN (
            SELECT MAX(createdAt) AS mostRecent,
                   timestampUTC
            FROM {b}
            WHERE type = "{CBActigraphRecord.type}"
                AND timestampUTC BETWEEN "{start}" AND "{end}"
                AND owner = "{owner}"
            GROUP BY timestampUTC
        ) maxCat ON records.timestampUTC = maxCat.timestampUTC
                 AND records.createdAt = maxCat.mostRecent
        """
