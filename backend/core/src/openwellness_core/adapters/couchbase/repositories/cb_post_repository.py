"""Couchbase repository for Post."""

from ....application.repositories.post_repository import PostRepository, SomePost
from ....domain.models.post import Post
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_post import CBPost
from .cb_base_repository import CBBaseRepository


class CBPostRepository(PostRepository, CBBaseRepository[SomePost, CBPost]):
    """Couchbase repository for the Post entity."""

    def __init__(
        self,
        repo: EntityRepository,
        entity_type: type[SomePost] = Post,
        persistence_type: type[CBPost] = CBPost,
    ) -> None:
        super().__init__(repo, entity_type, persistence_type)
        self.entity_type = entity_type

    def get_for_channel_between(
        self,
        channel: str,
        start: float = 0.0,
        end: float = 999999999999.9,
        conversation_id: str | None = None,
    ) -> list[SomePost]:
        q = self._build_query(channel, start, end, conversation_id)
        items = self.repo.get_by_query(q)
        return [self.init_entity_valid_fields(item) for item in items]

    def _build_query(
        self,
        channel: str,
        start: float,
        end: float,
        conversation_id: str | None,
    ) -> str:
        q = f"""
        SELECT {self.repo.bucket}.*, META().id, META().xattrs._sync.rev AS _rev
        FROM {self.repo.bucket}
        USE KEYS (SELECT RAW META().id
            FROM {self.repo.bucket}
            WHERE type="{CBPost.type}"
            AND '{channel}' IN channels
            AND createdAt BETWEEN {start} AND {end}
        """
        if conversation_id is not None:
            q += f"""AND conversationId='{conversation_id}'
            ORDER BY createdAt);"""
        else:
            q += "ORDER BY createdAt);"
        return q
