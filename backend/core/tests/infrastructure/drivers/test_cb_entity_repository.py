"""The Couchbase driver records the actor it was given and surfaces conflicts.

Two defects are guarded here, both of which are invisible from the return
value alone:

1. `update()` used to overwrite whatever actor the caller supplied with the
   fixed string `"scheduler"`, so every API-originated edit was attributed to
   a background service and the real identity was lost. The only assertion
   that proves this stopped is one against the **outgoing request body** —
   a test that checks the returned dict would pass against the broken code.

2. `_rev` reaching the driver populated (restored in 08-04) means Sync
   Gateway can now reject a stale write with a conflict where before it
   could not. That rejection has to arrive as something a caller can catch,
   not as a generic exception carrying a formatted string.

The conflict cases are driven through both detection signals independently
(HTTP 409, and a `conflict` error value in the body) so a Sync Gateway
version difference cannot make the handling silently one-sided.

The revision-placement assertions are a matched pair — present in the URL,
absent from the body — and they exist to stop a future reader who believes
`_sanitize` drops the revision by mistake from "restoring" it into the body,
where Sync Gateway ignores it and optimistic concurrency quietly dies.

No network, no container: `requests.post`/`requests.put` are monkeypatched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from openwellness_core.adapters.exceptions import RevisionConflictError
from openwellness_core.infrastructure.drivers import cb_entity_repository
from openwellness_core.infrastructure.drivers.cb_entity_repository import (
    CBEntityRepository,
)

SG_URL = "http://example/sg"

# Shaped like a real Sync Gateway revision id (generation-hash) rather than a
# placeholder, so a formatting assumption cannot hide behind a short string.
REV = "3-9f2c1a4b7e0d5c68a1b3f4e2d7c9b0a5"
NEXT_REV = "4-1d0c8b7a6e5f4d3c2b1a09f8e7d6c5b4"

# The machine-actor spelling 08-07 formalizes. Used here so these tests
# double as documentation of the intended value shape.
ACTOR = "system:weight-sync"

# What a document arrives carrying — deliberately *not* `ACTOR`, so the
# stamping assertions can tell "the argument won" from "the input passed
# through untouched".
STALE_ACTOR = "coach:c-1"

DOC_ID = "w-1"


@dataclass
class FakeCouchbaseConfig:
    url: str
    username: str
    password: str
    bucket_name: str


@dataclass
class FakeSyncGatewayConfig:
    url: str

    def get_url(self) -> str:
        return self.url


@dataclass
class SentRequest:
    """One captured outgoing HTTP call."""

    method: str
    url: str
    body: dict


class FakeResponse:
    """The two bits of a `requests.Response` the driver actually reads."""

    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


@dataclass
class Transport:
    """Records outgoing writes and replays a queued response for each."""

    responses: list[FakeResponse]
    sent: list[SentRequest] = field(default_factory=list)

    def _record(self, method: str, url: str, json: dict) -> FakeResponse:
        # A *copy* of the body: the driver mutates `obj` after the call (it
        # writes the returned id/rev back onto it), so holding the same dict
        # would let the assertions read post-response state and pass against
        # a driver that never sent the value at all.
        self.sent.append(SentRequest(method=method, url=url, body=dict(json)))
        return self.responses.pop(0)

    def post(self, url: str, json: dict, **_: Any) -> FakeResponse:
        return self._record("POST", url, json)

    def put(self, url: str, json: dict, **_: Any) -> FakeResponse:
        return self._record("PUT", url, json)

    @property
    def only(self) -> SentRequest:
        assert len(self.sent) == 1, f"expected one request, got {len(self.sent)}"
        return self.sent[0]


@pytest.fixture()
def driver() -> Any:
    """A fresh driver instance.

    `CBEntityRepository.__new__` enforces a process-wide singleton, so the
    cached instance has to be cleared on both sides of the test or the
    per-test config never takes effect.
    """
    CBEntityRepository._instance = None
    repo = CBEntityRepository(
        couchbase=FakeCouchbaseConfig(
            url="couchbase://example",
            username="user",
            password="pass",
            bucket_name="spring",
        ),
        sync_gateway=FakeSyncGatewayConfig(url=SG_URL),
    )
    yield repo
    CBEntityRepository._instance = None


def _transport(
    monkeypatch: pytest.MonkeyPatch, *responses: FakeResponse
) -> Transport:
    transport = Transport(responses=list(responses))
    monkeypatch.setattr(cb_entity_repository.requests, "post", transport.post)
    monkeypatch.setattr(cb_entity_repository.requests, "put", transport.put)
    return transport


def _doc(**overrides: Any) -> dict:
    doc = {
        "id": DOC_ID,
        "_rev": REV,
        "type": "Weight",
        "owner": "p1",
        "channels": ["study:s1"],
        "updatedBy": STALE_ACTOR,
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_constructs_from_narrow_protocols_only():
    CBEntityRepository._instance = None

    couchbase = FakeCouchbaseConfig(
        url="couchbase://example",
        username="user",
        password="pass",
        bucket_name="bucket",
    )
    sync_gateway = FakeSyncGatewayConfig(url="http://example/sg")

    repo = CBEntityRepository(couchbase=couchbase, sync_gateway=sync_gateway)

    assert repo.connection_string == "couchbase://example"
    assert repo.username == "user"
    assert repo.password == "pass"
    assert repo.bucket_name == "bucket"
    assert repo.sync_gateway_url == "http://example/sg"

    CBEntityRepository._instance = None


# ---------------------------------------------------------------------------
# Actor stamping
# ---------------------------------------------------------------------------


def test_update_stamps_the_actor_argument_over_the_incoming_value(
    driver, monkeypatch
):
    """The argument wins, whatever the incoming dict claimed.

    This is the regression that matters: the driver previously substituted a
    fixed service name here, so an edit made by a coach was recorded as one
    made by the scheduler. Asserting on the *sent* body is the only thing
    that proves the substitution is gone.
    """
    transport = _transport(
        monkeypatch, FakeResponse({"id": DOC_ID, "rev": NEXT_REV})
    )

    driver.update(DOC_ID, _doc(), actor=ACTOR)

    assert transport.only.body["updatedBy"] == ACTOR
    assert transport.only.body["updatedBy"] != STALE_ACTOR


def test_create_stamps_the_actor_argument(driver, monkeypatch):
    """Creates and updates must agree about who acted.

    `create()` stamped nothing at all before this phase, so a created
    document carried whatever the entity happened to hold while a later edit
    of the same document carried the driver's own literal.
    """
    transport = _transport(
        monkeypatch, FakeResponse({"id": DOC_ID, "rev": "1-abc"})
    )

    driver.create(_doc(_rev=""), actor=ACTOR)

    assert transport.only.body["updatedBy"] == ACTOR
    assert transport.only.body["updatedBy"] != STALE_ACTOR


def test_update_without_an_actor_raises_at_the_call(driver, monkeypatch):
    """`actor` is required and keyword-only, so omitting it cannot go quiet.

    Keyword-only is the point: a positional third argument would be
    indistinguishable from a typo at a call site, and binding the wrong value
    into an audit field is worse than failing loudly.
    """
    _transport(monkeypatch, FakeResponse({"id": DOC_ID, "rev": NEXT_REV}))

    with pytest.raises(TypeError):
        driver.update(DOC_ID, _doc())  # pyright: ignore[reportCallIssue]


# ---------------------------------------------------------------------------
# Revision placement
# ---------------------------------------------------------------------------


def test_update_sends_the_revision_in_the_query_string_not_the_body(
    driver, monkeypatch
):
    """Matched pair: present in the URL, absent from the body.

    The Sync Gateway REST API reads the revision from `?rev=` and ignores a
    body-borne `_rev`. Moving it into the body would therefore disable
    optimistic concurrency without any visible failure, which is exactly the
    "fix" a reader who mistrusts `_sanitize` would reach for.
    """
    transport = _transport(
        monkeypatch, FakeResponse({"id": DOC_ID, "rev": NEXT_REV})
    )

    driver.update(DOC_ID, _doc(), actor=ACTOR)

    assert transport.only.url == f"{SG_URL}/{DOC_ID}?rev={REV}"
    assert "_rev" not in transport.only.body
    assert "id" not in transport.only.body


# ---------------------------------------------------------------------------
# Conflict surfacing
# ---------------------------------------------------------------------------


def test_a_409_response_raises_revision_conflict_error(driver, monkeypatch):
    """Signal one: the HTTP status, on its own.

    The body deliberately spells the error as something *other* than the
    exact `conflict` token, so this test fails if the status check is
    removed. A body carrying both signals would let either check alone keep
    the test green, and the point of checking two signals is lost the moment
    no test can tell them apart.
    """
    _transport(
        monkeypatch,
        FakeResponse(
            {
                "error": "Document update conflict",
                "reason": "Document revision conflict",
            },
            status_code=409,
        ),
    )

    with pytest.raises(RevisionConflictError) as excinfo:
        driver.update(DOC_ID, _doc(), actor=ACTOR)

    assert excinfo.value.doc_id == DOC_ID
    assert excinfo.value.attempted_rev == REV
    assert excinfo.value.reason == "Document revision conflict"


def test_a_conflict_body_raises_even_when_the_status_is_not_409(
    driver, monkeypatch
):
    """Signal two: the body, independent of the status.

    Sync Gateway 2.8 is the only authority on which signal it sets for a
    given rejection. Checking one alone would turn a version quirk into an
    untyped exception at the exact moment a caller most needs to tell a
    conflict apart from every other failure.
    """
    _transport(
        monkeypatch,
        FakeResponse(
            {"error": "conflict", "reason": "Document revision conflict"},
            status_code=200,
        ),
    )

    with pytest.raises(RevisionConflictError) as excinfo:
        driver.update(DOC_ID, _doc(), actor=ACTOR)

    assert excinfo.value.doc_id == DOC_ID
    assert excinfo.value.attempted_rev == REV


def test_a_non_conflict_error_still_raises_the_generic_exception(
    driver, monkeypatch
):
    """This task narrows one case; it does not restructure error handling."""
    _transport(
        monkeypatch,
        FakeResponse(
            {"error": "forbidden", "reason": "sync function rejected"},
            status_code=403,
        ),
    )

    with pytest.raises(CBEntityRepository.GenericException):
        driver.update(DOC_ID, _doc(), actor=ACTOR)


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_a_successful_update_returns_the_revision_sync_gateway_reported(
    driver, monkeypatch
):
    """The caller gets the *new* revision back, not the one it sent.

    Without this the next write from the same in-memory object would carry a
    revision Sync Gateway has already superseded, and would be rejected as
    stale by the very mechanism this phase restored.
    """
    _transport(monkeypatch, FakeResponse({"id": DOC_ID, "rev": NEXT_REV}))

    result = driver.update(DOC_ID, _doc(), actor=ACTOR)

    assert result["_rev"] == NEXT_REV
    assert result["id"] == DOC_ID
