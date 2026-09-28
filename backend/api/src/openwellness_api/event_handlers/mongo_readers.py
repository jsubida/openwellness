"""Mongo reads for the event-handler routes (D-02: reads only).

Later plans add the device reader here.
"""

from __future__ import annotations

from typing import Any, Final, cast

from bson import ObjectId

STUDIES: Final = "studies"  # api/server/models/study.js collectionName
# Mongoose model ``Participant`` (api/server/models/mongoose/participant.js)
# pluralizes to the ``participants`` collection.
PARTICIPANTS: Final = "participants"


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
    """Frame's ``Participant.findByCouchId``: ``findOne({couchId})``.

    Returns the raw document. Mongoose would fill schema defaults on
    hydration (``isActive: true``, ``participantType: 0``); the SMART weight
    path compares with ``=== false`` and ``=== 3``, which a missing field
    fails exactly as the default does, so no defaults are applied here.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def find_by_couch_id(self, couch_id: object) -> dict[str, Any] | None:
        return self._db[PARTICIPANTS].find_one({"couchId": couch_id})

    def find_by_id(self, participant_id: object) -> dict[str, Any] | None:
        return None


class MongoDeviceReader:
    """Stub (RED)."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def first_by_serial_number(self, serial_number: str) -> dict[str, Any] | None:
        return None
