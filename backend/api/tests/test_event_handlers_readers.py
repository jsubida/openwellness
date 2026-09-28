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
    DESIGN_DOC,
    VIEW_NAME,
    CouchbaseViewSettingsReader,
)
from openwellness_api.event_handlers.mongo_readers import MongoStudyReader
from openwellness_api.event_handlers.ports import (
    ComponentSettingsReader,
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
