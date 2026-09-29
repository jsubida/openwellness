"""StudyComponentSetting reads through the Couchbase view frame already uses.

Frame's ``requireComponentSetting`` calls ``StudyComponentSetting.fetchIn``
(``api/server/models/couchbase/studyComponentSetting.js``) and takes
``setting[0]``. That is a view query, not N1QL, and this reader issues the
same one:

- design doc ``studyComponentSetting``, view
  ``byStudyAndComponentTypeAndCreatedAt``;
- key range ``[studyId, cType, 0]``..``[studyId, cType, 99999999999999]``,
  end inclusive;
- ``stale(BEFORE)``, which frame's SDK-4 shim maps to ``RequestPlus``.

Why a view and not N1QL (10-RESEARCH answer 4):

- frame already runs this exact view in production, so it adds zero new
  index risk on ``spring`` (an uncovered N1QL query could fall back to a
  primary scan or fail);
- rows come back ascending by key, so the first row is the OLDEST setting
  for the study and type, ties ordered by the view engine. OpenWellness's
  N1QL repositories take ``results[-1]``, the newest, which would enqueue a
  different task than frame for any study holding more than one setting.

The SMART weight path (D-04, placement 7A) also reads the owner's latest
Condition through frame's ``Condition.fetchLatest``
(``api/server/models/couchbase/condition.js``), again a view:

- design doc ``condition``, view ``byOwnerAndWeekAndCreatedAt``;
- key range ``[owner, -999, 0]``..``[owner, 999, 999999999999]``, end
  inclusive, ``reduce(false)``;
- no ``stale``: ``couchbase-admin.js`` sends a scan consistency only for an
  explicit ``stale``, so the server default applies and none is sent here;
- ``fetch`` maps rows to their ``value`` and ``fetchLatest`` takes the LAST
  row (``rows.slice(-1)[0]``), the newest by week then ``createdAt``.
"""

from __future__ import annotations

from typing import Any, Final

from couchbase.options import ViewOptions
from couchbase.views import ViewScanConsistency

DESIGN_DOC: Final = "studyComponentSetting"
VIEW_NAME: Final = "byStudyAndComponentTypeAndCreatedAt"

# fetchIn's range bounds on createdAt, verbatim.
_CREATED_AT_MIN: Final = 0
_CREATED_AT_MAX: Final = 99999999999999


class CouchbaseViewSettingsReader:
    """``StudyComponentSetting.fetchIn(cbAdmin, studyId, cType)[0]``.

    ``bucket`` is a Couchbase SDK ``Bucket`` (anything with ``view_query``).
    """

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    def first(self, study_id: object, component_type: int) -> dict[str, Any] | None:
        # The study id goes into the key unchanged: the SDK JSON-serializes
        # it. Callers holding an ObjectId pass its 24-hex string, which is how
        # an ObjectId serializes in frame's view key.
        options = ViewOptions(
            startkey=[study_id, component_type, _CREATED_AT_MIN],
            endkey=[study_id, component_type, _CREATED_AT_MAX],
            inclusive_end=True,
            scan_consistency=ViewScanConsistency.REQUEST_PLUS,
        )
        result = self._bucket.view_query(DESIGN_DOC, VIEW_NAME, options)
        row = next(iter(result.rows()), None)
        if row is None:
            return None
        # base.js topLevelProperties: the row value is the document, with
        # ``id`` set from the row id.
        return {**row.value, "id": row.id}


CONDITION_DESIGN_DOC: Final = "condition"
CONDITION_VIEW_NAME: Final = "byOwnerAndWeekAndCreatedAt"

# Condition.fetch's default bounds (startWeek -999, endWeek 999) and its
# createdAt bounds, verbatim.
_WEEK_MIN: Final = -999
_WEEK_MAX: Final = 999
_CONDITION_CREATED_AT_MIN: Final = 0
_CONDITION_CREATED_AT_MAX: Final = 999999999999


class CouchbaseViewConditionReader:
    """``Condition.fetchLatest(owner)``: the owner's newest Condition, or ``None``.

    ``bucket`` is a Couchbase SDK ``Bucket`` (anything with ``view_query``).
    Read-only (D-02).
    """

    def __init__(self, bucket: Any) -> None:
        self._bucket = bucket

    def latest(self, owner: object) -> dict[str, Any] | None:
        options = ViewOptions(
            startkey=[owner, _WEEK_MIN, _CONDITION_CREATED_AT_MIN],
            endkey=[owner, _WEEK_MAX, _CONDITION_CREATED_AT_MAX],
            inclusive_end=True,
            reduce=False,
        )
        result = self._bucket.view_query(
            CONDITION_DESIGN_DOC, CONDITION_VIEW_NAME, options
        )
        latest: dict[str, Any] | None = None
        for row in result.rows():
            latest = row.value
        # ``if (latest)``: a document value is always an object, so only an
        # empty result gives null.
        return latest
