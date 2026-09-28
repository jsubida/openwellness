"""Mongo reads for the event-handler routes (stub)."""

from __future__ import annotations

from typing import Any


class MongoStudyReader:
    def __init__(self, db: Any) -> None:
        self._db = db

    def find_by_id(self, study_id: object) -> dict[str, Any] | None:
        return None
