"""AppRepository interface."""

from abc import abstractmethod

from ...domain.models.app import App
from .base_crud_repository import BaseCrudRepository


class AppRepository(BaseCrudRepository[App, dict]):
    """Port for the App entity."""

    @abstractmethod
    def create_app(
        self, name: str, unlistedLink: bool = True, *, actor: str
    ) -> App:
        """Create a new App.

        ``actor`` carries the same contract as
        :meth:`BaseCrudRepository.create`, which this method writes through.
        A named-entry-point wrapper around a write is still a write; letting
        one omit the actor would leave a hole in exactly the shape this phase
        closes.
        """
