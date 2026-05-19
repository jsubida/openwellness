"""SurveyResultRepository interface."""

from abc import abstractmethod
from typing import Generic, TypeVar

from ...domain.models.survey_result import SurveyResult
from .base_crud_repository import BaseCrudRepository

SomeSurveyResult = TypeVar("SomeSurveyResult", bound=SurveyResult)


class SurveyResultRepository(
    BaseCrudRepository[SomeSurveyResult, str], Generic[SomeSurveyResult]
):
    """Port for the SurveyResult entity."""

    @abstractmethod
    def get_survey_results_on(
        self, owner: str, date: str, **kwargs
    ) -> SomeSurveyResult | None:
        """Get survey results for a participant on a date."""

    @abstractmethod
    def get_survey_results_between(
        self, owner: str, start: str, end: str, **kwargs
    ) -> list[SomeSurveyResult]:
        """Get survey results for a participant between two dates."""
