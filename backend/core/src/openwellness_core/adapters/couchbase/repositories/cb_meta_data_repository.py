"""Couchbase repository for MetaData."""

from typing import Optional

from ....application.repositories.meta_data_repository import (
    MetaDataRepository,
    SomeMetaData,
)
from ....domain.models.meta_data import MetaData
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_meta_data import CBMetaData
from .cb_base_repository import CBBaseRepository


class CBMetaDataRepository(
    MetaDataRepository, CBBaseRepository[SomeMetaData, CBMetaData]
):
    """Couchbase repository for the MetaData entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeMetaData] = MetaData,
        persistence_type: type[CBMetaData] = CBMetaData,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_related_id(
        self, related_id: str, ordering: str = "createdAt"
    ) -> list[SomeMetaData]:
        q = self._build_query(related_id=related_id, ordering=ordering)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def get_for_owner(
        self,
        owner: str,
        related_id: Optional[str],
        ordering: str = "createdAt",
    ) -> list[SomeMetaData]:
        q = self._build_query(owner_id=owner, related_id=related_id, ordering=ordering)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def get_for_study_id(
        self, study_id: str, ordering: str = "createdAt"
    ) -> list[SomeMetaData]:
        q = self._build_query(study_id=study_id, ordering=ordering)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_query(
        self,
        owner_id: Optional[str] = None,
        related_id: Optional[str] = None,
        study_id: Optional[str] = None,
        ordering: str = "createdAt",
    ) -> str:
        q = f"""
        SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
        FROM {self.repo.bucket}
        WHERE type="{CBMetaData.type}"
        """
        if owner_id is not None:
            q += f'AND owner="{owner_id}" '
        else:
            q += "AND owner IS NOT MISSING "

        if study_id is not None:
            q += f'AND studyId="{study_id}" '
        else:
            q += "AND studyId IS NOT MISSING "

        if related_id is not None:
            q += f'AND relatedId="{related_id}" '
        else:
            q += "AND relatedId IS NOT MISSING "
        q += f"ORDER BY studyId, {ordering};"
        return q
