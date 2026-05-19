"""Couchbase repository for CPAPSession."""

from typing import Generic

from arrow import Arrow

from ....application.repositories.cpap_session_repository import (
    CPAPSessionRepository,
    SomeCPAPSession,
)
from ....domain.models.cpap_session import CPAPSession
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_cpap_session import CBCPAPSession
from .cb_base_repository import CBBaseRepository


class CBCPAPSessionRepository(
    CPAPSessionRepository,
    CBBaseRepository[SomeCPAPSession, CBCPAPSession],
    Generic[SomeCPAPSession],
):
    """Couchbase repository for the CPAPSession entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeCPAPSession] = CPAPSession,
        persistence_type: type[CBCPAPSession] = CBCPAPSession,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def create_from(self, d: dict) -> SomeCPAPSession:
        cs = self.init_entity_valid_fields(d)
        return self.create(cs)

    def get_for_owner(self, owner_id: str, arg: Arrow) -> SomeCPAPSession | None:
        q = self._build_get_query(owner_id, arg)
        items = self.repo.get_by_query(q)
        if len(items) > 1:
            raise ValueError(
                f"{len(items)} CPAPSession found for owner {owner_id} on date {arg}"
            )
        return self.init_entity_valid_fields(items[0]) if len(items) == 1 else None

    def get_for_owner_between(
        self, owner_id: str, start: Arrow, end: Arrow
    ) -> list[SomeCPAPSession]:
        q = self._build_get_between_query(owner_id, start, end)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_get_between_query(self, owner_id: str, start: Arrow, end: Arrow) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBCPAPSession.type}"
                AND owner = "{owner_id}"
                AND dateOfSleep BETWEEN "{start.format('YYYY-MM-DD')}" AND "{end.format('YYYY-MM-DD')}"
            ORDER BY dateOfSleep, createdAt DESC
        """

    def _build_get_query(self, owner_id: str, arg: Arrow) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBCPAPSession.type}"
                AND owner = "{owner_id}"
                AND dateOfSleep = "{arg.format('YYYY-MM-DD')}"
            ORDER BY dateOfSleep, createdAt DESC
        """
