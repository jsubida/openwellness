"""Couchbase repository for UserSettings."""

from typing import Type, TypeVar

from ....application.repositories.user_settings_repository import (
    UserSettingsRepository,
)
from ....domain.models.user_settings import UserSettings
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_user import CBUserSettings
from .cb_base_repository import CBBaseRepository

SomeUserSettings = TypeVar("SomeUserSettings", bound=UserSettings)


class CBUserSettingsRepository(
    UserSettingsRepository, CBBaseRepository[SomeUserSettings, CBUserSettings]
):
    """Couchbase repository for the UserSettings entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeUserSettings] = UserSettings,
        persistence_type: type[CBUserSettings] = CBUserSettings,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_owner(self, owner_id: str) -> SomeUserSettings | None:
        b = self.repo.bucket
        q = (
            f"SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev "
            f"FROM {b} "
            f'WHERE type="{CBUserSettings.type}" '
            f'AND owner="{owner_id}" '
            "ORDER BY createdAt DESC "
            "LIMIT 1"
        )
        fetched = self.get_by_query(q)
        return fetched[0] if len(fetched) > 0 else None

    def get_all_for_owner(self, owner_id: str) -> list[SomeUserSettings]:
        b = self.repo.bucket
        q = (
            f"SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev "
            f"FROM {b} "
            f'WHERE type="{CBUserSettings.type}" '
            f'AND owner="{owner_id}" '
            "ORDER BY createdAt DESC"
        )
        return self.get_by_query(q)
