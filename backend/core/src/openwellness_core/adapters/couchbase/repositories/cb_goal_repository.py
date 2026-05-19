"""Couchbase repository for Goal."""

from typing import Generic

from arrow import Arrow

from ....application.repositories.goal_repository import GoalRepository, SomeGoal
from ....domain.models.goal import Goal
from ....domain.models.goal.kind import Kind, SomeKind, SomeKindArg
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_goal import CBGoal
from .cb_base_repository import CBBaseRepository


class CBGoalRepository(
    GoalRepository, CBBaseRepository[SomeGoal, CBGoal], Generic[SomeGoal]
):
    """Couchbase repository for the Goal entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeGoal] = Goal,
        persistence_type: type[CBGoal] = CBGoal,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_owner(self, owner_id: str, arg: Arrow) -> SomeGoal | None:
        q = self.generate_query(owner_id, arg.floor("day"), arg.ceil("day"))
        goals = self.get_by_query(q)
        return None if len(goals) == 0 else goals[-1]

    def get_for_owner_between(self, owner_id: str, start: Arrow, end: Arrow) -> list:
        q = self.generate_query(owner_id, start, end)
        return self.get_by_query(q)

    def get_all_for_owner(self, owner_id: str, arg: Arrow) -> list[SomeGoal]:
        q = self.generate_query(owner_id, arg.floor("day"), arg.ceil("day"))
        return self.get_by_query(q)

    def get_all_for_owner_between(
        self, owner_id: str, start: Arrow, end: Arrow
    ) -> list[SomeGoal]:
        q = self.generate_query(owner_id, start, end, False)
        return self.get_by_query(q)

    def get_all_for_owner_by_kind(
        self, owner_id: str, arg: Arrow, kind: SomeKindArg | None = None
    ) -> list[SomeGoal]:
        return self.get_all_for_owner_by_kind_between(
            owner_id, arg.floor("day"), arg.ceil("day"), kind
        )

    def get_all_for_owner_by_kind_between(
        self,
        owner_id: str,
        start: Arrow,
        end: Arrow,
        kind: SomeKindArg | None = None,
    ) -> list[SomeGoal]:
        q = self.generate_query_by_kind(owner_id, start, end, kind, False)
        return self.get_by_query(q)

    def get_for_owner_by_kind(
        self, owner_id: str, arg: Arrow, kind: SomeKind | None = None
    ) -> SomeGoal | None:
        q = self.generate_query_by_kind(
            owner_id, arg.floor("day"), arg.ceil("day"), kind
        )
        goals = self.get_by_query(q)
        return None if len(goals) == 0 else goals[-1]

    def get_for_owner_by_kind_between(
        self,
        owner_id: str,
        start: Arrow,
        end: Arrow,
        kind: SomeKind | None = None,
    ) -> list[SomeGoal]:
        q = self.generate_query_by_kind(owner_id, start, end, kind)
        return self.get_by_query(q)

    def generate_query(
        self,
        owner_id: str,
        start: Arrow,
        end: Arrow,
        group_by_start=True,
        **kwargs,
    ) -> str:
        b = self.repo.bucket
        q = f"""
        SELECT goals.*
        FROM (
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBGoal.type}"
            AND owner = "{owner_id}"
            AND kind is MISSING
            AND startDate BETWEEN {start.timestamp()} AND {end.timestamp()}
            ORDER BY startDate, createdAt
        ) AS goals
        """
        if group_by_start:
            q += f"""
            INNER JOIN (
                SELECT
                max(createdAt) AS mostRecent,
                startDate
                FROM {b}
                WHERE
                type = "{CBGoal.type}"
                AND owner = "{owner_id}"
                AND kind is MISSING
                GROUP BY
                startDate
            ) maxCat ON goals.startDate = maxCat.startDate
            AND goals.createdAt = maxCat.mostRecent
            """
        return q

    def generate_query_by_kind(
        self,
        owner_id: str,
        start: Arrow,
        end: Arrow,
        kind: SomeKindArg | None,
        group_by_start=True,
    ) -> str:
        b = self.repo.bucket
        q = f"""
        SELECT goals.*
        FROM (
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type = "{CBGoal.type}"
            AND owner = "{owner_id}"
            AND startDate BETWEEN {start.timestamp()} AND {end.timestamp()}
            {self.generate_kind_expression(kind)}
            ORDER BY startDate, createdAt
        ) AS goals
        """
        if group_by_start:
            q += f"""
            INNER JOIN (
                SELECT
                max(createdAt) AS mostRecent,
                startDate
                FROM {b}
                WHERE
                type = "{CBGoal.type}"
                AND owner = "{owner_id}"
                {self.generate_kind_expression(kind)}
                GROUP BY
                startDate
            ) maxCat ON goals.startDate = maxCat.startDate
            AND goals.createdAt = maxCat.mostRecent
            """
        return q

    def generate_kind_expression(self, kind: SomeKindArg | None) -> str:
        if kind is None:
            return "AND kind IS NOT MISSING"
        elif isinstance(kind, (Kind, int)):
            return f"AND kind = {str(int(kind))}"
        elif isinstance(kind, list):
            return f"AND kind IN {[str(int(k)) for k in kind]}"
        raise Exception(f"Invalid `kind` type: {type(kind)}")
