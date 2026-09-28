"""Legacy study ids from ``STUDY_SPECIFIC`` (stub, implemented in 10-05)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

ENV_KEY: Final = "STUDY_SPECIFIC"


class LegacyStudyConfigError(Exception):
    """``STUDY_SPECIFIC`` is absent or unusable."""


@dataclass(frozen=True)
class LegacyStudyIds:
    smart: str | None = None
    fit2thrive: str | None = None
    mpower: str | None = None

    def contains(self, study_id: object) -> bool:
        raise NotImplementedError

    def is_smart(self, study_id: object) -> bool:
        raise NotImplementedError


class LegacyStudyIdsProvider:
    def __init__(self, load: Callable[[], str | None]) -> None:
        self._load = load

    @classmethod
    def from_process_env(cls) -> LegacyStudyIdsProvider:
        return cls(lambda: None)

    @classmethod
    def from_value(cls, raw: str | None) -> LegacyStudyIdsProvider:
        return cls(lambda: raw)

    @classmethod
    def of(cls, ids: LegacyStudyIds) -> LegacyStudyIdsProvider:
        return cls(lambda: None)

    def get(self) -> LegacyStudyIds:
        raise NotImplementedError
