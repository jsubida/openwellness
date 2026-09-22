"""Attribution reaches the repository from the HTTP boundary (D-15, DATA-04).

The per-layer proofs already exist: 08-06 proved the adapters stamp what they
are given, and 08-07 proved the repository ports require an actor at all. What
neither covers is the seam between them — that the identity the API *resolved*
for a request is the identity the repository is *told about*. A route could
type-check, stamp ``updated_by`` on the entity, and still hand the repository
some other value; that is exactly the class of defect DATA-03 was.

So these tests assert against the fake's ``actor_log``, not against the
response body. The response only shows what the entity carries; the log shows
what the write was told, which is the thing that becomes ``updatedBy`` in
storage.

R-10 (ROADMAP Phase 9 Success Criterion 6): identity on a write comes only
from a verified bearer token. These tests were INVERTED by Phase 9's R-10 work
(09-06), not replaced: before it, ``X-Principal-Id`` named the actor and an
unauthenticated write stored ``anonymous``. Now an authenticated bearer write
attributes to the token's subject, an unauthenticated write is refused with
401, and a client-supplied principal header on a write is refused with 403 —
and both refusals store nothing. The diff against ``main`` is the record of
exactly which contract changed. See ``specs/006-write-route-auth/``.
"""

from __future__ import annotations

from typing import Any

from openwellness_core.application.repositories import WeightRepository


def _weight_repo(fakes: dict[type, Any]) -> Any:
    return fakes[WeightRepository]


# Inverted by Phase 9's R-10 work (09-06 Task 1; specs/006-write-route-auth/).
# Each test below previously asserted the pre-R-10 contract; its name and
# subject are kept so the diff shows the contract change, not a new suite.


def test_create_names_the_requesting_principal(
    client, fakes, auth_headers
) -> None:
    r = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers=auth_headers("coach-alice"),
    )
    assert r.status_code == 201, r.text
    weight_id = r.json()["name"].rsplit("/", 1)[1]

    repo = _weight_repo(fakes)
    # The actor is the verified token's subject — the only identity source.
    assert repo.actor_log == [("create", weight_id, "coach-alice")]
    # The entity's audit field and the actor named at the write agree — they
    # are set by different code paths (stamp_audit vs. the call site), so
    # asserting both is what proves they have not drifted apart.
    assert repo.store[weight_id].updated_by == "coach-alice"


def test_patch_names_the_requesting_principal(
    client, fakes, auth_headers
) -> None:
    created = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers=auth_headers("coach-alice"),
    )
    assert created.status_code == 201, created.text
    weight_id = created.json()["name"].rsplit("/", 1)[1]

    r = client.patch(
        f"/v1/users/user-1/weights/{weight_id}",
        json={"weight": 179.0},
        headers=auth_headers("coach-bob"),
    )
    assert r.status_code == 200, r.text

    repo = _weight_repo(fakes)
    # A DIFFERENT principal edited the record than created it. The original
    # defect was a write recording the writing *service* rather than the
    # acting person, which would make these two indistinguishable.
    assert repo.last_actor == "coach-bob"
    assert repo.actor_log[-1] == ("save", weight_id, "coach-bob")
    assert repo.store[weight_id].updated_by == "coach-bob"


def test_delete_names_who_archived_the_record(
    client, fakes, auth_headers
) -> None:
    """The delete route had NO identity in scope before Phase 8 (T-08-41).

    An archived record under a 6-year retention policy is the copy most likely
    to be read back years later, so "who removed this" is precisely what a
    future reader wants — and it must be a verified identity, not a header.
    """
    created = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers=auth_headers("coach-alice"),
    )
    assert created.status_code == 201, created.text
    weight_id = created.json()["name"].rsplit("/", 1)[1]

    r = client.delete(
        f"/v1/users/user-1/weights/{weight_id}",
        headers=auth_headers("coach-carol"),
    )
    assert r.status_code == 204, r.text

    repo = _weight_repo(fakes)
    assert repo.actor_log[-1] == ("archive", weight_id, "coach-carol")


def test_unattributed_request_records_anonymous_not_a_service_name(
    client, fakes
) -> None:
    """An unauthenticated write is refused and stores nothing (R-10).

    Before R-10 this write succeeded and recorded ``anonymous``. Now there is
    no un-named write to record at all: the guard answers 401 before the route
    runs, so the repository is never told about it — neither as ``anonymous``
    nor as a fixed service name.
    """
    r = client.post("/v1/users/user-1/weights", json={"weight": 180.5})
    assert r.status_code == 401, r.text

    repo = _weight_repo(fakes)
    assert repo.actor_log == []
    assert repo.last_actor is None


def test_principal_header_without_bearer_is_refused_and_stores_nothing(
    client, fakes
) -> None:
    """``X-Principal-Id`` no longer names anyone on a write: 403, nothing stored."""
    r = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers={"X-Principal-Id": "coach-alice"},
    )
    assert r.status_code == 403, r.text

    repo = _weight_repo(fakes)
    assert repo.actor_log == []


def test_valid_bearer_plus_principal_header_is_still_refused(
    client, fakes, auth_headers
) -> None:
    """Presenting a credential does not buy the right to also name a principal.

    This is the case a reader most easily assumes is permitted (T-09-38): the
    bearer is valid, so why not honour the header too? Because the header is
    exactly the forgeable identity R-10 removes; accepting it alongside a
    token would let any authenticated caller write as someone else.
    """
    headers = {**auth_headers("coach-alice"), "X-Principal-Id": "coach-mallory"}
    r = client.post(
        "/v1/users/user-1/weights", json={"weight": 180.5}, headers=headers
    )
    assert r.status_code == 403, r.text

    repo = _weight_repo(fakes)
    assert repo.actor_log == []
