"""StudyComponentSetting reads through frame's Couchbase view (stub)."""

from __future__ import annotations

from typing import Any, Final

DESIGN_DOC: Final = "studyComponentSetting"
VIEW_NAME: Final = "byStudyAndComponentTypeAndCreatedAt"


class CouchbaseViewSettingsReader:
    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        return None
