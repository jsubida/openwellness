"""Couchbase repository for StudySettings."""

from typing import Generic, Type

from ....application.repositories.study_settings_repository import (
    SomeStudySettings,
    StudySettingsRepository,
)
from ....domain.models.study_settings import StudySettings
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_study_settings import CBStudySettings
from .cb_base_repository import CBBaseRepository


class CBStudySettingsRepository(
    StudySettingsRepository,
    CBBaseRepository[SomeStudySettings, CBStudySettings],
    Generic[SomeStudySettings],
):
    """Couchbase repository for the StudySettings entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeStudySettings] = StudySettings,
        persistence_type: type[CBStudySettings] = CBStudySettings,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_study_id(self, study_id: str) -> SomeStudySettings | None:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type="{CBStudySettings.type}"
            AND studyId="{study_id}"
            ORDER BY createdAt
        """
        results = self.repo.get_by_query(q)
        result = None if len(results) == 0 else results[-1]
        return self.init_entity_valid_fields(result) if result else None
