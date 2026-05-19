"""CPAPSession domain model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import arrow

from ..value_objects.sleep_metric import SleepMetric
from .base_owner_entity import BaseOwnerEntity

usage_string_format = "YYYY-MM-DD_HH:mm:ss"


@dataclass(kw_only=True)
class CPAPSession(BaseOwnerEntity):
    """A single session of CPAP data. May be multiple per day."""

    clinical_metrics: Dict[str, Dict[str, float]]
    date_of_sleep: str
    device_id: Dict[str, str]
    patient_interface: Dict[str, str]
    receipt_time: str
    resp_events: Dict[str, float]
    session_date: str
    settings: Dict[str, float]
    usage: Dict[str, Any]

    leak_threshold: float = 0.4

    @property
    def earliest_mask_on_time(self) -> arrow.Arrow:
        mask_on_times = self.usage["maskOn"]
        earliest = arrow.get(mask_on_times[0], usage_string_format)
        for time in mask_on_times:
            current = arrow.get(time, usage_string_format)
            if current < earliest:
                earliest = current
        return earliest

    @property
    def leak(self) -> float:
        return float(self.clinical_metrics["leak"]["95"])

    @property
    def latest_mask_off_time(self) -> arrow.Arrow:
        mask_off_times = self.usage["maskOff"]
        latest = arrow.get(mask_off_times[0], usage_string_format)
        for time in mask_off_times:
            current = arrow.get(time, usage_string_format)
            if current > latest:
                latest = current
        return latest

    @property
    def mask_usage_in_seconds(self) -> int:
        total_seconds = 0
        for mask_on, mask_off in self.mask_on_off_pairs():
            total_seconds += int((mask_off - mask_on).total_seconds())
        return total_seconds

    def mask_on_off_pairs(self) -> List[tuple[arrow.Arrow, arrow.Arrow]]:
        mask_on_times = self.usage["maskOn"]
        mask_off_times = self.usage["maskOff"]
        pairs = []
        for i in range(len(mask_on_times)):
            mask_on_time = arrow.get(mask_on_times[i], usage_string_format)
            mask_off_time = arrow.get(mask_off_times[i], usage_string_format)
            pairs.append((mask_on_time, mask_off_time))
        return pairs

    def metrics(self) -> List[SleepMetric]:
        metrics: list[SleepMetric] = []
        for mask_on, mask_off in self.mask_on_off_pairs():
            metrics.append(
                SleepMetric(
                    start=mask_on,
                    end=mask_off,
                    duration_in_seconds=int((mask_off - mask_on).total_seconds()),
                )
            )
        return metrics

    def update_from(self, session: CPAPSession):
        self.clinical_metrics = session.clinical_metrics
        self.device_id = session.device_id
        self.patient_interface = session.patient_interface
        self.receipt_time = session.receipt_time
        self.resp_events = session.resp_events
        self.session_date = session.session_date
        self.settings = session.settings

        usage = session.usage
        if usage["maskOn"][0] not in self.usage["maskOn"]:
            self.usage["duration"] = (
                f'{int(usage["duration"]) + int(self.usage["duration"])}'
            )
            self.usage["maskOn"] += usage["maskOn"]
            self.usage["maskOff"] += usage["maskOff"]
        else:
            self.usage = usage
