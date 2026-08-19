"""FitbitRecordRepository interface."""

from abc import abstractmethod

from ...domain.models.fitbit_record import FitbitRecord
from ..dtos.activity_data_dto import ActivityDataInputDTO
from .owner_crud_repository import OwnerCrudRepository


class FitbitRecordRepository(OwnerCrudRepository[FitbitRecord, str]):
    """Interface for FitbitRecord."""

    @abstractmethod
    def create_from_notification(
        self,
        pid: str,
        fitbit_date: str,
        study_id: str,
        data: ActivityDataInputDTO,
        *,
        actor: str,
    ) -> FitbitRecord:
        """Create a FitbitRecord from a notification.

        ``actor`` names the identity recorded on the written document, as on
        :meth:`BaseCrudRepository.create`, which this method writes through.
        A vendor notification is a machine write: build the value with
        :func:`openwellness_core.application.actors.system_actor` rather than
        attributing it to ``pid``, who did not perform it.
        """
