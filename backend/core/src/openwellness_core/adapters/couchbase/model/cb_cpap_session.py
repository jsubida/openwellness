"""Couchbase persistence for CPAPSession."""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from .cb_base_owner_entity import CBBaseOwnerEntity


class CBCPAPSession(CBBaseOwnerEntity):
    """Persistence for CPAPSession."""

    model_config = ConfigDict(
        populate_by_name=True, extra="ignore", arbitrary_types_allowed=True
    )

    type: ClassVar[str] = "CPAPSession"

    clinical_metrics: Any = Field(alias="clinicalMetrics", default=None)
    date_of_sleep: Any = Field(alias="dateOfSleep", default=None)
    device_id: Any = Field(alias="deviceID", default=None)
    leak_threshold: Any = Field(alias="leakThreshold", default=None)
    patient_interface: Any = Field(alias="patientInterface", default=None)
    receipt_time: Any = Field(alias="receiptTime", default=None)
    resp_events: Any = Field(alias="respEvents", default=None)
    session_date: Any = Field(alias="sessionDate", default=None)
    settings: Any = Field(alias="set", default=None)
    usage: Any = None
