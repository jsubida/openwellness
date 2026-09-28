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
