"""Sync Gateway admin-interface client for sync users (RED stub)."""

from __future__ import annotations

import requests

from ...application.repositories.sync_user_repository import SyncUserRepository
from ...domain.models.sync_user import SyncUser


class SyncUserProvisioningError(Exception):
    """A Sync Gateway admin call on a user failed."""

    def __init__(self, operation: str, status: int | None, reason: str) -> None:
        self.operation = operation
        self.status = status
        self.reason = reason
        super().__init__(operation)


class SGAdminUserRepository(SyncUserRepository[SyncUser]):
    """Stub: every method is a no-op until the GREEN commit."""

    def __init__(
        self,
        admin_db_url: str,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base = admin_db_url

    def provision(self, name: str, password: str, admin_channels: list[str]) -> None:
        return None

    def save(self, user: SyncUser) -> SyncUser:
        return user

    def get_by_id(self, entity_id: str) -> SyncUser | None:
        return None

    def delete(self, name: str) -> None:
        return None
