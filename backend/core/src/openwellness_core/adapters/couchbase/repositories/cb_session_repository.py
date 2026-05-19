"""Couchbase repository for Session."""

from typing import List, Type, TypeVar

from ....application.repositories.session_repository import SessionRepository
from ....domain.models.session import Session
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_session import CBSession
from .cb_base_repository import CBBaseRepository

SomeSession = TypeVar("SomeSession", bound=Session)


class CBSessionRepository(
    SessionRepository[SomeSession], CBBaseRepository[SomeSession, CBSession]
):
    """Couchbase repository for the Session entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: Type[SomeSession] = Session,
        persistence_type: type[CBSession] = CBSession,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def fetch_sessions_in_range(
        self,
        owner: str,
        start: float = 0.0,
        end: float = 9999999999999.9,
        require_session_type: bool = False,
        session_type: int | None = None,
    ) -> List[SomeSession]:
        b = self.repo.bucket
        q = f"""
            SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {b}
            WHERE type="{CBSession.type}"
            AND owner="{owner}"
            AND timeStartInMS BETWEEN {start} AND {end}
        """
        if require_session_type:
            if session_type is not None:
                q += f"AND sessionType={session_type} "
            else:
                q += "AND sessionType IS MISSING "
        q += "ORDER BY timeStartInMS, createdAt"
        return self.get_by_query(q)

    def count_sessions_in_range(
        self,
        owner: str,
        start: float = 0.0,
        end: float = 9999999999999.9,
        require_session_type: bool = False,
        session_type: int | None = None,
    ) -> int:
        b = self.repo.bucket
        q = f"""
            SELECT COUNT(*) AS num
            FROM {b}
            WHERE type="{CBSession.type}"
            AND owner="{owner}"
            AND timeStartInMS BETWEEN {start} AND {end}
        """
        if require_session_type:
            if session_type is not None:
                q += f"AND sessionType={session_type} "
            else:
                q += "AND sessionType IS MISSING "
        return self.execute_query(q)[0]["num"]
