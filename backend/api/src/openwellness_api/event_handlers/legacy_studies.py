"""Frame's legacy study ids, from the shared ``STUDY_SPECIFIC`` key (D-03, D-04).

Frame parses the key once at boot and keeps three of its ids:

- ``api/config.js:18``: ``JSON.parse(process.env.STUDY_SPECIFIC)``;
- ``api/config.js:112-115``: ``studyID.smart = smartId``,
  ``studyID.fit2Thrive = fit2ThriveId``, ``studyID.mPower = mPowerId``;
- ``api/server/api/event-handlers.js:28-37``:
  ``legacyStudyIDs = [fttStudyID, smartStudyID, mPowerID]``.

``activity`` and ``weight`` branch on ``legacyStudyIDs.includes(studyId)``.
For a legacy study frame never enqueues the route's observer (D-03), and for
the SMART study ``weight`` takes the rerandomization path (D-04).

``ow_api`` reads the SAME opserver ``.env`` key, passed through unchanged, and
never an ``OW_``-prefixed copy: a second copy could drift and silently enqueue
``activityObserver`` for a legacy study (T-10-24).

Fail closed. Frame cannot boot without the key (``JSON.parse(undefined)``
throws). ``ow_api`` boots, but a route that needs the list raises
:class:`LegacyStudyConfigError` when the key is absent, empty, not JSON, not a
JSON object, or holds a non-string id; the route answers hapi 500 and never
guesses that a study is non-legacy. A present object missing one of the three
keys behaves as frame does: that id is ``undefined`` and matches no study.
Error messages name the key, never its value.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

ENV_KEY: Final = "STUDY_SPECIFIC"

# STUDY_SPECIFIC key -> LegacyStudyIds field, in frame's config.js order.
_KEYS: Final = (("smartId", "smart"), ("fit2ThriveId", "fit2thrive"), ("mPowerId", "mpower"))


class LegacyStudyConfigError(Exception):
    """``STUDY_SPECIFIC`` is absent or unusable. The message never holds its value."""


@dataclass(frozen=True)
class LegacyStudyIds:
    """The three ids frame treats as legacy studies. ``None`` is an absent key."""

    smart: str | None = None
    fit2thrive: str | None = None
    mpower: str | None = None

    def contains(self, study_id: object) -> bool:
        """``legacyStudyIDs.includes(studyId)``.

        ``includes`` compares without coercion, so only a string equal to a
        present id matches: a number never equals a string id, and ``null``
        never equals an absent key (``undefined``).
        """
        if not isinstance(study_id, str):
            return False
        return any(
            study_id == legacy
            for legacy in (self.smart, self.fit2thrive, self.mpower)
            if legacy is not None
        )

    def is_smart(self, study_id: object) -> bool:
        """``studyId === smartStudyID``."""
        return (
            isinstance(study_id, str)
            and self.smart is not None
            and study_id == self.smart
        )


def parse_study_specific(raw: str | None) -> LegacyStudyIds:
    """Parse the key as frame does, raising where frame could not boot."""
    if raw is None or not raw.strip():
        raise LegacyStudyConfigError(f"{ENV_KEY} is not set")
    try:
        document = json.loads(raw)
    except ValueError:
        raise LegacyStudyConfigError(f"{ENV_KEY} is not valid JSON") from None
    if not isinstance(document, dict):
        raise LegacyStudyConfigError(f"{ENV_KEY} is not a JSON object")
    ids: dict[str, str | None] = {}
    for key, field_name in _KEYS:
        value = document.get(key)
        if value is not None and not isinstance(value, str):
            raise LegacyStudyConfigError(f"{ENV_KEY}.{key} is not a string")
        ids[field_name] = value
    return LegacyStudyIds(**ids)


class LegacyStudyIdsProvider:
    """Parses ``STUDY_SPECIFIC`` on first use, once, and caches the outcome.

    Construction never reads or parses, so ``ow_api`` boots with the key
    unset. :meth:`get` is thread-safe; a failed parse raises on every call
    and is never cached as an empty (non-legacy) list.
    """

    def __init__(self, load: Callable[[], str | None]) -> None:
        self._load = load
        self._lock = threading.Lock()
        self._ids: LegacyStudyIds | None = None
        self._error: str | None = None

    @classmethod
    def from_process_env(cls) -> LegacyStudyIdsProvider:
        """Read ``STUDY_SPECIFIC`` from the process environment on first use."""
        return cls(lambda: os.environ.get(ENV_KEY))

    @classmethod
    def from_value(cls, raw: str | None) -> LegacyStudyIdsProvider:
        """Parse a given raw value, as if it were the environment's."""
        return cls(lambda: raw)

    @classmethod
    def of(cls, ids: LegacyStudyIds) -> LegacyStudyIdsProvider:
        """A provider holding already-parsed ids."""
        provider = cls(lambda: None)
        provider._ids = ids
        return provider

    def get(self) -> LegacyStudyIds:
        ids = self._ids
        if ids is not None:
            return ids
        with self._lock:
            if self._ids is None and self._error is None:
                try:
                    self._ids = parse_study_specific(self._load())
                except LegacyStudyConfigError as exc:
                    self._error = str(exc)
            if self._error is not None:
                raise LegacyStudyConfigError(self._error)
            assert self._ids is not None
            return self._ids
