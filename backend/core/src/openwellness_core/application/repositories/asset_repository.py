"""AssetRepository interface."""

from abc import abstractmethod
from typing import List, Optional, TypeVar

from ...domain.models.asset import Asset
from .base_crud_repository import BaseCrudRepository

SomeAsset = TypeVar("SomeAsset", bound=Asset)


class AssetRepository(BaseCrudRepository[SomeAsset, str]):
    """Port for the Asset entity."""

    @abstractmethod
    def fetch(
        self,
        study_id: str,
        kind: Optional[int] = None,
        week: Optional[int] = None,
        orderBy: str = "createdAt",
        **kwargs,
    ) -> List[SomeAsset]:
        """Fetch assets based on the provided criteria."""
