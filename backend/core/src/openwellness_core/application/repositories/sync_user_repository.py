"""SyncUserRepository interface."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ...domain.models.sync_user import SyncUser

SomeSyncUser = TypeVar("SomeSyncUser", bound="SyncUser")


class SyncUserRepository(ABC, Generic[SomeSyncUser]):
    """Interface for the SyncUser repository."""

    @abstractmethod
    def get_by_id(self, entity_id: str) -> SomeSyncUser | None:
        """Get a SyncUser by its ID."""

    @abstractmethod
    def save(self, user: SomeSyncUser) -> SomeSyncUser:
        """Save a SyncUser's channel grants.

        ``save`` never changes a password: a ``SyncUser`` carries none, so an
        implementation sends only the name and the admin channels. Credentials
        are set through :meth:`provision`.
        """

    @abstractmethod
    def provision(self, name: str, password: str, admin_channels: list[str]) -> bool:
        """Create the user, or update it if it already exists.

        Idempotent: provisioning the same name twice leaves one user with the
        given password and admin channels. Returns ``True`` when this call
        created the user and ``False`` when it updated an existing one, so a
        caller undoing a failed create deletes only a user it created.
        """

    @abstractmethod
    def delete(self, name: str) -> None:
        """Remove the user. Idempotent: deleting a missing user is not an error."""
