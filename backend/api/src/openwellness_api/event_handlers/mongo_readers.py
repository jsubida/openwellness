"""Mongo reads for the event-handler routes (D-02: reads only)."""

from __future__ import annotations

from typing import Any, Final, cast

from bson import ObjectId

STUDIES: Final = "studies"  # api/server/models/study.js collectionName
# Mongoose model ``Participant`` (api/server/models/mongoose/participant.js)
# pluralizes to the ``participants`` collection.
PARTICIPANTS: Final = "participants"
# Mongoose model ``device`` (api/server/models/mongoose/device.js) pluralizes
# to the ``devices`` collection.
DEVICES: Final = "devices"


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
        """``Participant.findById(new ObjectID(pid))`` (ActiGraph pre chain).

        ``new ObjectID(null)`` is a fresh id that matches nothing, so ``None``
        returns ``None`` without a query. A malformed id raises
        ``bson.errors.InvalidId`` (any other type ``TypeError``), which the
        route renders as hapi 500, as frame's constructor throw does.
        """
        if participant_id is None:
            return None
        oid = ObjectId(cast("str | ObjectId", participant_id))
        return self._db[PARTICIPANTS].find_one({"_id": oid})


class MongoDeviceReader:
    """Frame's ``Device.find({serialNumber})`` then ``device[0]``.

    ``find_one`` returns the first match in natural order, as ``find()[0]``
    does. Only a string is ever used as the filter value: anything else
    could be a query operator (``{"$gt": ""}``) or, as frame's Mongoose
    does with ``undefined``, match an arbitrary device and enqueue a job for
    the wrong participant (T-10-32). The route answers a bare 200 without
    calling this for an absent or non-scalar ``subjectId``.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def first_by_serial_number(self, serial_number: str) -> dict[str, Any] | None:
        if not isinstance(serial_number, str):
            raise TypeError("serialNumber must be a string")
        return self._db[DEVICES].find_one({"serialNumber": serial_number})
