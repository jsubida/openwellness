"""The liveness path writes no access-log line (D-16).

The test fixture never runs the lifespan, so the filter cannot be observed
through the test client; these tests assert it structurally instead: the
filter drops uvicorn access records for the liveness path, keeps every other
record, and installation attaches it to ``uvicorn.access`` exactly once.
"""

from __future__ import annotations

import logging

from openwellness_api.main import (
    LIVENESS_PATH,
    LivenessAccessLogFilter,
    install_liveness_access_log_filter,
)


def _access_record(path: str) -> logging.LogRecord:
    # uvicorn.access formats: '%s - "%s %s HTTP/%s" %d'
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", path, "1.1", 200),
        None,
    )


def test_liveness_access_record_is_dropped() -> None:
    f = LivenessAccessLogFilter()
    assert f.filter(_access_record(LIVENESS_PATH)) is False
    assert f.filter(_access_record(f"{LIVENESS_PATH}?probe=edge")) is False


def test_other_records_pass() -> None:
    f = LivenessAccessLogFilter()
    assert f.filter(_access_record("/v1/users/user-1/weights")) is True
    assert f.filter(_access_record("/healthz-extra")) is True
    plain = logging.LogRecord("x", logging.INFO, __file__, 0, "hello", None, None)
    assert f.filter(plain) is True


def test_install_attaches_once_to_uvicorn_access() -> None:
    logger = logging.getLogger("uvicorn.access")
    install_liveness_access_log_filter()
    install_liveness_access_log_filter()
    ours = [f for f in logger.filters if isinstance(f, LivenessAccessLogFilter)]
    assert len(ours) == 1
