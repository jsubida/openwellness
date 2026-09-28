"""The two reads the Sync Gateway handlers make, against frame's own sources.

- ``CouchbaseViewSettingsReader`` is ``StudyComponentSetting.fetchIn(...)[0]``
  (``api/server/models/couchbase/studyComponentSetting.js``): the view
  ``studyComponentSetting/byStudyAndComponentTypeAndCreatedAt``, key range
  ``[studyId, cType, 0]``..``[studyId, cType, 99999999999999]`` inclusive,
  ``stale(BEFORE)`` which the SDK-4 shim maps to ``RequestPlus``. Rows come
  back ascending by key, so the first row is the OLDEST setting. The row's
  ``value`` is the document with ``id`` set from the row id
  (``base.js topLevelProperties``).
- ``MongoStudyReader`` is ``Study.findById`` on collection ``studies``.

The SMART weight path (D-04, placement 7A) adds two more:

- ``CouchbaseViewConditionReader`` is ``Condition.fetchLatest(owner)``
  (``api/server/models/couchbase/condition.js``): the view
  ``condition/byOwnerAndWeekAndCreatedAt``, key range
  ``[owner, -999, 0]``..``[owner, 999, 999999999999]`` inclusive,
  ``reduce(false)`` and no ``stale``, so no scan consistency is sent
  (``couchbase-admin.js`` maps only an explicit ``stale``). ``fetch`` maps the
  rows to their values and ``fetchLatest`` takes the LAST one.
- ``MongoParticipantReader`` is ``Participant.findByCouchId`` on collection
  ``participants``: ``findOne({couchId})``.

The ActiGraph pre chain (HOOK-02) adds two Mongo reads
(``api/server/api/event-handlers.js:343-370``):

- ``MongoDeviceReader`` is ``Device.find({serialNumber})[0]`` on collection
  ``devices`` (Mongoose model ``device``): the first match in natural order.
- ``MongoParticipantReader.find_by_id`` is
  ``Participant.findById(new ObjectID(pid))``: ``new ObjectID(null)`` is a
  fresh id that matches nothing, and a malformed id throws (hapi 500).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import mongomock
import pytest
from bson import ObjectId
from bson.errors import InvalidId
from couchbase.logic.views import ViewQuery
from couchbase.options import ViewOptions
from couchbase.views import ViewScanConsistency

from openwellness_api.event_handlers.couchbase_views import (
    CONDITION_DESIGN_DOC,
    CONDITION_VIEW_NAME,
    DESIGN_DOC,
    VIEW_NAME,
    CouchbaseViewConditionReader,
    CouchbaseViewSettingsReader,
)
from openwellness_api.event_handlers.mongo_readers import (
    MongoDeviceReader,
    MongoParticipantReader,
    MongoStudyReader,
)
from openwellness_api.event_handlers.ports import (
    ComponentSettingsReader,
    ConditionReader,
    DeviceReader,
    EventHandlerDeps,
    ParticipantReader,
    StudyReader,
)


@dataclass
class Row:
    id: str
    key: list[Any]
    value: Any


class FakeViewResult:
    def __init__(self, rows: list[Row]) -> None:
        self._rows = rows

    def rows(self) -> Any:
        return iter(self._rows)


class FakeBucket:
    """Records every ``view_query`` call and returns scripted rows."""

    def __init__(self, rows: list[Row] | None = None) -> None:
        self.rows = rows or []
        self.calls: list[tuple[str, str, tuple[Any, ...], dict[str, Any]]] = []

    def view_query(
        self, design_doc: str, view_name: str, *options: Any, **kwargs: Any
    ) -> FakeViewResult:
        self.calls.append((design_doc, view_name, options, kwargs))
        return FakeViewResult(self.rows)


def _setting_row(doc_id: str, created_at: int, **fields: Any) -> Row:
    value = {"studyId": "s1", "componentType": 2, "createdAt": created_at, **fields}
    return Row(id=doc_id, key=["s1", 2, created_at], value=value)


# --------------------------------------------------------------------------- #
# CouchbaseViewSettingsReader
# --------------------------------------------------------------------------- #


def test_settings_reader_satisfies_the_port() -> None:
    reader: ComponentSettingsReader = CouchbaseViewSettingsReader(FakeBucket())
    assert reader is not None


def test_queries_frames_view_by_name() -> None:
    bucket = FakeBucket()

    CouchbaseViewSettingsReader(bucket).first("s1", 2)

    assert len(bucket.calls) == 1
    design_doc, view_name, _, _ = bucket.calls[0]
    assert (design_doc, view_name) == (
        "studyComponentSetting",
        "byStudyAndComponentTypeAndCreatedAt",
    )
    assert (DESIGN_DOC, VIEW_NAME) == (design_doc, view_name)


def test_key_range_is_frames_inclusive_range_with_request_plus() -> None:
    bucket = FakeBucket()

    CouchbaseViewSettingsReader(bucket).first("s1", 2)

    _, _, options, kwargs = bucket.calls[0]
    assert kwargs == {}
    assert len(options) == 1
    opts = options[0]
    assert isinstance(opts, ViewOptions)
    expected = ViewOptions(
        startkey=["s1", 2, 0],
        endkey=["s1", 2, 99999999999999],
        inclusive_end=True,
        scan_consistency=ViewScanConsistency.REQUEST_PLUS,
    )
    assert dict(opts) == dict(expected)


def test_installed_sdk_consumes_the_option_names() -> None:
    """The keyword names reach the SDK's query object (SDK 4.6.1, A5)."""
    bucket = FakeBucket()
    CouchbaseViewSettingsReader(bucket).first("s1", 2)
    _, _, options, _ = bucket.calls[0]

    query = ViewQuery.create_view_query_object(
        "spring", DESIGN_DOC, VIEW_NAME, *options
    )

    assert query.startkey == json.dumps(["s1", 2, 0])
    assert query.endkey == json.dumps(["s1", 2, 99999999999999])
    assert query.inclusive_end is True
    assert query.consistency == ViewScanConsistency.REQUEST_PLUS


def test_study_id_passes_through_unchanged() -> None:
    bucket = FakeBucket()
    oid = "5f0c1a2b3c4d5e6f7a8b9c0d"

    CouchbaseViewSettingsReader(bucket).first(oid, 1)

    opts = bucket.calls[0][2][0]
    assert opts["startkey"] == [oid, 1, 0]
    assert opts["endkey"] == [oid, 1, 99999999999999]


def test_returns_the_first_row_which_is_the_oldest() -> None:
    older = _setting_row("old-doc", 1000, fitbitHeartObserver="task.old")
    newer = _setting_row("new-doc", 2000, fitbitHeartObserver="task.new")
    bucket = FakeBucket([older, newer])

    setting = CouchbaseViewSettingsReader(bucket).first("s1", 2)

    assert setting is not None
    assert setting["fitbitHeartObserver"] == "task.old"
    assert setting["id"] == "old-doc"


def test_row_value_merged_with_row_id_overriding_any_value_id() -> None:
    row = _setting_row("row-id", 1000, id="stale-id")
    bucket = FakeBucket([row])

    setting = CouchbaseViewSettingsReader(bucket).first("s1", 2)

    assert setting == {
        "studyId": "s1",
        "componentType": 2,
        "createdAt": 1000,
        "id": "row-id",
    }
    assert row.value["id"] == "stale-id"  # the row itself is not mutated


def test_zero_rows_is_none() -> None:
    assert CouchbaseViewSettingsReader(FakeBucket([])).first("s1", 2) is None


def test_module_uses_no_n1ql() -> None:
    import openwellness_api.event_handlers.couchbase_views as module

    source = open(module.__file__).read()
    assert "SELECT" not in source.upper().replace("SELECTS", "")
    assert ".query(" not in source


# --------------------------------------------------------------------------- #
# MongoStudyReader
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db() -> Any:
    return mongomock.MongoClient().db


def test_study_reader_satisfies_the_port(db: Any) -> None:
    reader: StudyReader = MongoStudyReader(db)
    assert reader is not None


def test_find_by_id_returns_the_studies_document(db: Any) -> None:
    oid = ObjectId()
    db["studies"].insert_one({"_id": oid, "name": "Fit Study", "other": 1})

    study = MongoStudyReader(db).find_by_id(str(oid))

    assert study is not None
    assert study["name"] == "Fit Study"
    assert study["_id"] == oid


def test_find_by_id_accepts_an_object_id(db: Any) -> None:
    oid = ObjectId()
    db["studies"].insert_one({"_id": oid, "name": "Fit Study"})

    study = MongoStudyReader(db).find_by_id(oid)

    assert study is not None
    assert study["name"] == "Fit Study"


def test_unknown_id_is_none(db: Any) -> None:
    assert MongoStudyReader(db).find_by_id(str(ObjectId())) is None


def test_none_is_none_without_a_query(db: Any) -> None:
    class Exploding:
        def __getitem__(self, name: str) -> Any:
            raise AssertionError("no query for a None id")

    assert MongoStudyReader(Exploding()).find_by_id(None) is None


def test_malformed_id_raises_invalid_id(db: Any) -> None:
    with pytest.raises(InvalidId):
        MongoStudyReader(db).find_by_id("not-an-object-id")


# --------------------------------------------------------------------------- #
# CouchbaseViewConditionReader (SMART weight, D-04)
# --------------------------------------------------------------------------- #


def _condition_row(doc_id: str, week: int, created_at: int, **fields: Any) -> Row:
    value = {"owner": "o1", "week": week, "createdAt": created_at, **fields}
    return Row(id=doc_id, key=["o1", week, created_at], value=value)


def test_condition_reader_satisfies_the_port() -> None:
    reader: ConditionReader = CouchbaseViewConditionReader(FakeBucket())
    assert reader is not None


def test_condition_reader_queries_frames_view_by_name() -> None:
    bucket = FakeBucket()

    CouchbaseViewConditionReader(bucket).latest("o1")

    assert len(bucket.calls) == 1
    design_doc, view_name, _, _ = bucket.calls[0]
    assert (design_doc, view_name) == ("condition", "byOwnerAndWeekAndCreatedAt")
    assert (CONDITION_DESIGN_DOC, CONDITION_VIEW_NAME) == (design_doc, view_name)


def test_condition_key_range_is_frames_with_reduce_false_and_no_consistency() -> None:
    bucket = FakeBucket()

    CouchbaseViewConditionReader(bucket).latest("o1")

    _, _, options, kwargs = bucket.calls[0]
    assert kwargs == {}
    assert len(options) == 1
    opts = options[0]
    assert isinstance(opts, ViewOptions)
    expected = ViewOptions(
        startkey=["o1", -999, 0],
        endkey=["o1", 999, 999999999999],
        inclusive_end=True,
        reduce=False,
    )
    assert dict(opts) == dict(expected)
    assert "scan_consistency" not in dict(opts)


def test_installed_sdk_sends_no_scan_consistency_for_conditions() -> None:
    """Frame's ``Condition.fetch`` sets no ``stale``: the server default applies."""
    bucket = FakeBucket()
    CouchbaseViewConditionReader(bucket).latest("o1")
    _, _, options, _ = bucket.calls[0]

    query = ViewQuery.create_view_query_object(
        "spring", CONDITION_DESIGN_DOC, CONDITION_VIEW_NAME, *options
    )

    assert query.startkey == json.dumps(["o1", -999, 0])
    assert query.endkey == json.dumps(["o1", 999, 999999999999])
    assert query.inclusive_end is True
    assert query.reduce is False
    assert "scan_consistency" not in query.as_encodable()


def test_condition_reader_returns_the_last_row_value() -> None:
    first = _condition_row("c-1", 1, 1000, responderState=0)
    middle = _condition_row("c-2", 2, 2000, responderState=1)
    last = _condition_row("c-3", 3, 3000, responderState=2)
    bucket = FakeBucket([first, middle, last])

    condition = CouchbaseViewConditionReader(bucket).latest("o1")

    # fetch maps rows to ``value`` only; fetchLatest takes rows.slice(-1)[0].
    assert condition == last.value
    assert condition is not None
    assert condition["responderState"] == 2
    assert "id" not in condition


def test_condition_reader_zero_rows_is_none() -> None:
    assert CouchbaseViewConditionReader(FakeBucket([])).latest("o1") is None


def test_condition_owner_passes_through_unchanged() -> None:
    bucket = FakeBucket()

    CouchbaseViewConditionReader(bucket).latest(None)

    opts = bucket.calls[0][2][0]
    assert opts["startkey"] == [None, -999, 0]
    assert opts["endkey"] == [None, 999, 999999999999]


# --------------------------------------------------------------------------- #
# MongoParticipantReader (SMART weight, D-04)
# --------------------------------------------------------------------------- #


def test_participant_reader_satisfies_the_port(db: Any) -> None:
    reader: ParticipantReader = MongoParticipantReader(db)
    assert reader is not None


def test_find_by_couch_id_returns_the_participants_document(db: Any) -> None:
    pid = ObjectId()
    db["participants"].insert_one(
        {"_id": pid, "couchId": "c1", "isActive": True, "participantType": 0}
    )
    db["participants"].insert_one({"_id": ObjectId(), "couchId": "c2"})

    participant = MongoParticipantReader(db).find_by_couch_id("c1")

    assert participant is not None
    assert participant["_id"] == pid
    assert participant["isActive"] is True
    assert participant["participantType"] == 0


def test_find_by_couch_id_queries_couch_id_only(db: Any) -> None:
    db["participants"].insert_one({"_id": ObjectId(), "userId": "c1"})
    db["participants"].insert_one({"_id": "c1", "couchId": "other"})

    assert MongoParticipantReader(db).find_by_couch_id("c1") is None


def test_find_by_couch_id_unknown_is_none(db: Any) -> None:
    assert MongoParticipantReader(db).find_by_couch_id("nobody") is None


# --------------------------------------------------------------------------- #
# MongoParticipantReader.find_by_id (ActiGraph, HOOK-02)
# --------------------------------------------------------------------------- #


def test_find_participant_by_id_returns_the_participants_document(db: Any) -> None:
    pid, study = ObjectId(), ObjectId()
    db["participants"].insert_one({"_id": pid, "couchId": "c1", "studyId": study})
    db["participants"].insert_one({"_id": ObjectId(), "couchId": "c2"})

    for key in (str(pid), pid):
        participant = MongoParticipantReader(db).find_by_id(key)
        assert participant is not None
        assert participant["couchId"] == "c1"
        assert participant["studyId"] == study


def test_find_participant_by_id_unknown_is_none(db: Any) -> None:
    db["participants"].insert_one({"_id": ObjectId(), "couchId": "c1"})
    assert MongoParticipantReader(db).find_by_id(str(ObjectId())) is None


def test_find_participant_by_id_none_is_none_without_a_query() -> None:
    class Exploding:
        def __getitem__(self, name: str) -> Any:
            raise AssertionError("no query for a None id")

    # `new ObjectID(null)` is a fresh id, so frame's findById finds nothing.
    assert MongoParticipantReader(Exploding()).find_by_id(None) is None


def test_find_participant_by_id_malformed_raises(db: Any) -> None:
    with pytest.raises(InvalidId):
        MongoParticipantReader(db).find_by_id("not-an-object-id")


def test_find_participant_by_id_never_matches_on_couch_id(db: Any) -> None:
    pid = ObjectId()
    db["participants"].insert_one({"_id": ObjectId(), "couchId": str(pid)})
    assert MongoParticipantReader(db).find_by_id(str(pid)) is None


# --------------------------------------------------------------------------- #
# MongoDeviceReader (ActiGraph, HOOK-02)
# --------------------------------------------------------------------------- #


def test_device_reader_satisfies_the_port(db: Any) -> None:
    reader: DeviceReader = MongoDeviceReader(db)
    assert reader is not None


def test_first_by_serial_number_returns_the_first_match_in_natural_order(
    db: Any,
) -> None:
    first, second = ObjectId(), ObjectId()
    db["devices"].insert_one({"_id": ObjectId(), "serialNumber": "11111"})
    db["devices"].insert_one({"_id": first, "serialNumber": "28953", "participantId": ObjectId()})
    db["devices"].insert_one({"_id": second, "serialNumber": "28953", "participantId": ObjectId()})

    device = MongoDeviceReader(db).first_by_serial_number("28953")

    assert device is not None
    assert device["_id"] == first


def test_first_by_serial_number_unknown_is_none(db: Any) -> None:
    db["devices"].insert_one({"_id": ObjectId(), "serialNumber": "11111"})
    assert MongoDeviceReader(db).first_by_serial_number("28953") is None


def test_first_by_serial_number_queries_serial_number_only(db: Any) -> None:
    db["devices"].insert_one({"_id": ObjectId(), "subjectId": "28953", "serialNumber": "x"})
    db["participants"].insert_one({"_id": ObjectId(), "serialNumber": "28953"})
    assert MongoDeviceReader(db).first_by_serial_number("28953") is None


@pytest.mark.parametrize("serial", [None, {"$gt": ""}, ["28953"], 28953])
def test_first_by_serial_number_refuses_anything_but_a_string(
    db: Any, serial: Any
) -> None:
    # A non-string filter value could be a query operator or match every
    # device (T-10-32). The route only ever passes a string.
    db["devices"].insert_one({"_id": ObjectId(), "serialNumber": "28953"})
    with pytest.raises(TypeError):
        MongoDeviceReader(db).first_by_serial_number(serial)


# --------------------------------------------------------------------------- #
# Un-wired defaults: loud, never a silent skip
# --------------------------------------------------------------------------- #


def test_unwired_condition_and_participant_readers_raise() -> None:
    deps = EventHandlerDeps(
        settings=CouchbaseViewSettingsReader(FakeBucket()),
        studies=MongoStudyReader(mongomock.MongoClient().db),
        publisher=_NoPublisher(),
    )
    with pytest.raises(RuntimeError, match="not wired"):
        deps.conditions.latest("o1")
    with pytest.raises(RuntimeError, match="not wired"):
        deps.participants.find_by_couch_id("c1")
    with pytest.raises(RuntimeError, match="not wired"):
        deps.participants.find_by_id(str(ObjectId()))
    with pytest.raises(RuntimeError, match="not wired"):
        deps.devices.first_by_serial_number("28953")


class _NoPublisher:
    def publish(self, task_name: str, args: list[Any]) -> None:
        raise AssertionError("no publish expected")


# --------------------------------------------------------------------------- #
# Production wiring (the lifespan's build_event_handler_deps)
# --------------------------------------------------------------------------- #


def test_build_event_handler_deps_wires_the_real_readers_and_publisher(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openwellness_api.event_handlers import build_event_handler_deps
    from openwellness_api.event_handlers.celery_producer import (
        CeleryTaskPublisher,
        ProducerSettings,
    )

    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    bucket = FakeBucket([_setting_row("doc-1", 1)])

    deps = build_event_handler_deps(
        bucket=bucket, db=db, producer_settings=ProducerSettings()
    )

    assert isinstance(deps.settings, CouchbaseViewSettingsReader)
    assert isinstance(deps.studies, MongoStudyReader)
    assert isinstance(deps.publisher, CeleryTaskPublisher)
    assert deps.settings.first("s1", 2) == {**_setting_row("doc-1", 1).value, "id": "doc-1"}
    # The SMART weight readers share the same bucket and Mongo handle.
    assert isinstance(deps.conditions, CouchbaseViewConditionReader)
    assert isinstance(deps.participants, MongoParticipantReader)
    assert deps.conditions.latest("s1") == _setting_row("doc-1", 1).value
    assert bucket.calls[-1][:2] == ("condition", "byOwnerAndWeekAndCreatedAt")
    db["participants"].insert_one({"_id": ObjectId(), "couchId": "c9"})
    found = deps.participants.find_by_couch_id("c9")
    assert found is not None
    assert found["couchId"] == "c9"
    # The ActiGraph readers share the same Mongo handle.
    assert isinstance(deps.devices, MongoDeviceReader)
    db["devices"].insert_one({"_id": ObjectId(), "serialNumber": "28953"})
    device = deps.devices.first_by_serial_number("28953")
    assert device is not None
    assert device["serialNumber"] == "28953"
    by_id = deps.participants.find_by_id(found["_id"])
    assert by_id is not None
    assert by_id["couchId"] == "c9"


def test_unset_broker_url_logs_one_warning_naming_only_the_key(
    db: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from openwellness_api.event_handlers import build_event_handler_deps
    from openwellness_api.event_handlers.celery_producer import ProducerSettings

    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)

    with caplog.at_level("WARNING"):
        build_event_handler_deps(
            bucket=FakeBucket(), db=db, producer_settings=ProducerSettings()
        )

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "CELERY_BROKER_URL" in warnings[0].getMessage()


def test_set_broker_url_logs_nothing_and_never_its_value(
    db: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from openwellness_api.event_handlers import build_event_handler_deps
    from openwellness_api.event_handlers.celery_producer import ProducerSettings

    secret = "redis://:sentinel-pass-91c2@redis:6379/0"
    monkeypatch.setenv("CELERY_BROKER_URL", secret)

    with caplog.at_level("DEBUG"):
        build_event_handler_deps(
            bucket=FakeBucket(), db=db, producer_settings=ProducerSettings()
        )

    assert [r for r in caplog.records if r.levelname == "WARNING"] == []
    assert "sentinel-pass-91c2" not in caplog.text
