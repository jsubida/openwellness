"""Couchbase repository for Asset."""

from typing import Generic, List, Optional, Type

from ....application.repositories.asset_repository import AssetRepository, SomeAsset
from ....domain.models.asset import Asset
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_asset import CBAsset
from .cb_base_repository import CBBaseRepository


class CBAssetRepository(
    AssetRepository, CBBaseRepository[SomeAsset, CBAsset], Generic[SomeAsset]
):
    """Repository for the Asset entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeAsset] = Asset,
        persistence_type: type[CBAsset] = CBAsset,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type: Type[SomeAsset] = entity_type

    def fetch(
        self,
        study_id: str,
        kind: Optional[int] = None,
        week: Optional[int] = None,
        orderBy: str = "createdAt",
        **kwargs,
    ) -> List[SomeAsset]:
        b = self.repo.bucket
        kind_filter = f"AND kind={kind}" if kind is not None else ""
        week_filter = f"AND week={week}" if week is not None else ""
        additional_filters = " ".join(
            [f"AND {key}={value}" for key, value in kwargs.items()]
        )
        return self.get_by_query(
            f"""
            SELECT {b}.*, META().id, META().xattrs._sync.rev AS _rev
            FROM {b}
            WHERE type="{CBAsset.type}"
            AND studyId="{study_id}"
            {kind_filter}
            {week_filter}
            {additional_filters}
            ORDER BY {orderBy}
        """
        )
