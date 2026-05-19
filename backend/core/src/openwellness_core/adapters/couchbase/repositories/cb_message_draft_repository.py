"""Couchbase repository for MessageDraft."""

from ....application.repositories.message_draft_repository import MessageDraftRepository
from ....domain.models.message_draft import MessageDraft
from ....infrastructure.interfaces.entity_repository import EntityRepository
from ..model.cb_conversation import CBMessageDraft
from .cb_base_repository import CBBaseRepository


class CBMessageDraftRepository(
    MessageDraftRepository, CBBaseRepository[MessageDraft, CBMessageDraft]
):
    """Couchbase repository for the MessageDraft entity."""

    def __init__(
        self,
        repo: EntityRepository,
        persistence_type: type[CBMessageDraft] = CBMessageDraft,
    ) -> None:
        super().__init__(repo, MessageDraft, persistence_type)

    def get_for_study_subtype(
        self,
        study_id: str,
        subtype: int,
        week: int | None = None,
        day: int | None = None,
    ) -> list[MessageDraft]:
        b = self.repo.bucket
        q = (
            f"SELECT {b}.*, meta().id, meta().xattrs._sync.rev as _rev "
            f"FROM {b} USE KEYS (SELECT RAW meta().id "
            f"FROM {b} "
            f'WHERE type="{CBMessageDraft.type}" '
            f'AND studyId="{study_id}" AND subtype={subtype} '
        )
        if week:
            q += f"AND week={week} "
        if day:
            q += f"AND day={day} "
        q += ") ORDER BY subtype, week, day, createdAt"
        return self.get_by_query(q)
