"""Mongo reads for the event-handler routes (D-02: reads only).

Later plans add the participant and device readers here.
"""

from __future__ import annotations

from typing import Any, Final, cast

from bson import ObjectId

STUDIES: Final = "studies"  # api/server/models/study.js collectionName


class MongoStudyReader:
    """Frame's ``Study.findById``.

    ``db`` is anything indexable by collection name: a pymongo ``Database``
    or OpenWellness's ``MDBCollectionRepository``.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def find_by_id(self, study_id: object) -> dict[str, Any] | None:
        if study_id is None:
            return None
        # A malformed id raises bson.errors.InvalidId, which the handler
        # renders as hapi 500, as frame's findById cast failure does.
        # Any other type raises TypeError, also a 500.
        oid = ObjectId(cast("str | ObjectId", study_id))
        return self._db[STUDIES].find_one({"_id": oid}, {"name": 1})


class MongoParticipantReader:
    """Stub (10-05 Task 2 RED)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def find_by_couch_id(self, couch_id: object) -> dict[str, Any] | None:
        return None
