"""Couchbase repository for SurveyResult."""

from typing import List, Optional, Type, TypeVar, Union

from ....application.repositories.survey_result_repository import (
    SomeSurveyResult,
    SurveyResultRepository,
)
from ....domain.models.survey_result import SurveyResult
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_survey_result import CBSurveyResult
from .cb_base_repository import CBBaseRepository

T = TypeVar("T", bound=int)
KindArg = Union[T, List[T]]


class CBSurveyResultRepository(
    SurveyResultRepository[SomeSurveyResult],
    CBBaseRepository[SomeSurveyResult, CBSurveyResult],
):
    """Couchbase repository for the SurveyResult entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeSurveyResult] = SurveyResult,
        persistence_type: type[CBSurveyResult] = CBSurveyResult,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_survey_results_on(
        self, owner: str, date: str, **kwargs
    ) -> SomeSurveyResult | None:
        q = self._generate_query(owner, date, date, **kwargs)
        results = self.get_by_query(q)
        return results[0] if results else None

    def get_survey_results_between(
        self, owner: str, start: str, end: str, **kwargs
    ) -> list[SomeSurveyResult]:
        q = self._generate_query(owner, start, end, **kwargs)
        return self.get_by_query(q)

    def _generate_query(self, owner: str, start: str, end: str, **kwargs) -> str:
        b = self.repo.bucket
        q = (
            f"SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev "
            f"FROM {b} "
            f'WHERE type="{CBSurveyResult.type}" '
            f'AND owner="{owner}" '
            f'AND surveyDate BETWEEN "{start}" AND "{end}" '
        )
        if "kind" in kwargs:
            q += self._kind_expression(kwargs["kind"])
        q += "ORDER BY surveyDate, createdAt"
        return q

    def _kind_expression(self, kind: Optional[KindArg]) -> str:
        if kind is None:
            return "AND (kind IS MISSING OR kind IS NULL)"
        if hasattr(kind, "real"):
            return f"AND kind = {str(kind)}"
        if hasattr(kind, "append"):
            return f"AND kind IN {str(kind)}"
        raise Exception(f"Invalid `kind` type: {type(kind)}")
