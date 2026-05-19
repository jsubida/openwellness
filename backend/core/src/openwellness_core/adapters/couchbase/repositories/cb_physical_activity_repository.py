"""Couchbase repository for PhysicalActivity."""

from typing import List

import arrow

from ....application.repositories.physical_activity_repository import (
    PhysicalActivityRepository,
)
from ....domain.models.physical_activity import PhysicalActivity
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_physical_activity import CBPhysicalActivity
from .cb_base_repository import CBBaseRepository


class CBPhysicalActivityRepository(
    PhysicalActivityRepository,
    CBBaseRepository[PhysicalActivity, CBPhysicalActivity],
):
    """Couchbase repository for the PhysicalActivity entity."""

    def __init__(
        self,
        repo: EntityRepository,
        persistence_type: type[CBPhysicalActivity] = CBPhysicalActivity,
    ) -> None:
        super().__init__(repo, PhysicalActivity, persistence_type)

    def fetch_all_in_range(
        self, owner: str, start: float, end: float, descending: bool = False
    ) -> List[PhysicalActivity]:
        b = self.repo.bucket
        is_descending = "DESC" if descending else ""
        return self.get_by_query(
            f"""
            SELECT {b}.*, META().id, META().xattrs._sync.rev AS _rev
            FROM {b}
            WHERE type="{CBPhysicalActivity.type}"
            AND owner='{owner}'
            AND dateOfActivity BETWEEN {start} AND {end}
            ORDER BY dateOfActivity {is_descending}, createdAt {is_descending}
        """
        )

    def fetch_for_week_of_date(self, owner: str, date: float) -> List[PhysicalActivity]:
        arrow_date = arrow.get(date).to("local")
        start = arrow_date.floor("week").timestamp()
        end = arrow_date.ceil("week").timestamp()
        return self.fetch_mvpa_in_range(owner, start, end)

    def fetch_for_date(self, owner: str, date: float) -> List[PhysicalActivity]:
        arrow_date = arrow.get(date).to("local")
        start = arrow_date.floor("day").timestamp()
        end = arrow_date.ceil("day").timestamp()
        return self.fetch_mvpa_in_range(owner, start, end)

    def fetch_mvpa_in_range(
        self, owner: str, start: float, end: float
    ) -> List[PhysicalActivity]:
        activities = self.fetch_all_in_range(owner, start, end)
        return [activity for activity in activities if activity.met >= 3]
