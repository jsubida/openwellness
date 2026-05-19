"""Couchbase repository for Conversations."""

from ....application.repositories.conversation_repository import (
    ConversationRepository,
    SomeConversation,
)
from ....domain.models.conversation import Conversation
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_conversation import CBConversation
from .cb_base_repository import CBBaseRepository


class CBConversationRepository(
    ConversationRepository, CBBaseRepository[SomeConversation, CBConversation]
):
    """Couchbase repository for the Conversation entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomeConversation] = Conversation,
        persistence_type: type[CBConversation] = CBConversation,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_filters(
        self, filters: list[Conversation.Filter]
    ) -> list[SomeConversation]:
        q = self._build_query(filters)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_filters(self, filters: list[Conversation.Filter]) -> str:
        clause = " AND ".join([f.n1ql() for f in filters])
        if len(filters) > 0:
            clause = f"AND {clause}"
        return clause

    def _build_query(self, filters: list[Conversation.Filter]) -> str:
        return f"""
            SELECT {self.repo.bucket}.*, meta().id, meta().xattrs._sync.rev as _rev
            FROM {self.repo.bucket}
            WHERE type = "{CBConversation.type}"
            {self._build_filters(filters)}
            ORDER BY kind, createdAt
        """
