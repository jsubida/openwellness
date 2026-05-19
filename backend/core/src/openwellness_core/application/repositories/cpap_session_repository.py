"""CPAPSessionRepository interface."""

from abc import abstractmethod
from typing import Generic, TypeVar

from arrow import Arrow

from ...domain.models.cpap_session import CPAPSession
from .owner_crud_repository import OwnerCrudRepository

SomeCPAPSession = TypeVar("SomeCPAPSession", bound=CPAPSession)


class CPAPSessionRepository(
    OwnerCrudRepository[SomeCPAPSession, Arrow],
    Generic[SomeCPAPSession],
):
    """Interface for the CPAPSession entity."""

    @abstractmethod
    def create_from(self, d: dict) -> SomeCPAPSession:
        """Create a CPAPSession from a dictionary."""
