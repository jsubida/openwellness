"""ParticipantGroupRepository interface."""

from abc import abstractmethod
from typing import Generic, TypeVar

from ...domain.models.participant_group import ParticipantGroup
from .base_crud_repository import BaseCrudRepository

SomeParticipantGroup = TypeVar("SomeParticipantGroup", bound=ParticipantGroup)


class ParticipantGroupRepository(
    BaseCrudRepository[SomeParticipantGroup, str], Generic[SomeParticipantGroup]
):
    """Interface for ParticipantGroup entity."""

    @abstractmethod
    def get_by_channel(self, channel: str) -> SomeParticipantGroup | None:
        """Fetch the ParticipantGroup by channel."""

    @abstractmethod
    def create_participant_group(
        self, owner: str, study_id: str, *, actor: str, **kwargs
    ) -> SomeParticipantGroup:
        """Create a new ParticipantGroup.

        ``actor`` names the identity recorded on the written document and
        carries the same contract as :meth:`BaseCrudRepository.create` — this
        method writes through :meth:`BaseCrudRepository.save`, so leaving it
        out here would reintroduce an implicit actor one call above the port
        that forbids one.

        ``owner`` is not that identity: it names the participant the group
        belongs to, which is frequently not who created it.
        """
