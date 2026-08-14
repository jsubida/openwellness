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
"""

from __future__ import annotations

from typing import Any

from openwellness_core.application.repositories import WeightRepository


def _weight_repo(fakes: dict[type, Any]) -> Any:
    return fakes[WeightRepository]


def test_create_names_the_requesting_principal(client, fakes) -> None:
    r = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers={"X-Principal-Id": "coach-alice"},
    )
    assert r.status_code == 201, r.text
    weight_id = r.json()["name"].rsplit("/", 1)[1]

    repo = _weight_repo(fakes)
    assert repo.actor_log == [("create", weight_id, "coach-alice")]
    # The entity's audit field and the actor named at the write agree — they
    # are set by different code paths (stamp_audit vs. the call site), so
    # asserting both is what proves they have not drifted apart.
    assert repo.store[weight_id].updated_by == "coach-alice"


def test_patch_names_the_requesting_principal(client, fakes) -> None:
    created = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers={"X-Principal-Id": "coach-alice"},
    )
    weight_id = created.json()["name"].rsplit("/", 1)[1]

    r = client.patch(
        f"/v1/users/user-1/weights/{weight_id}",
        json={"weight": 179.0},
        headers={"X-Principal-Id": "coach-bob"},
    )
    assert r.status_code == 200, r.text

    repo = _weight_repo(fakes)
    # A DIFFERENT principal edited the record than created it. The original
    # defect was a write recording the writing *service* rather than the
    # acting person, which would make these two indistinguishable.
    assert repo.last_actor == "coach-bob"
    assert repo.actor_log[-1] == ("save", weight_id, "coach-bob")
    assert repo.store[weight_id].updated_by == "coach-bob"


def test_delete_names_who_archived_the_record(client, fakes) -> None:
    """The delete route had NO identity in scope before this phase (T-08-41).

    An archived record under a 6-year retention policy is the copy most likely
    to be read back years later, so "who removed this" is precisely what a
    future reader wants and precisely what could not be answered.
    """
    created = client.post(
        "/v1/users/user-1/weights",
        json={"weight": 180.5},
        headers={"X-Principal-Id": "coach-alice"},
    )
    weight_id = created.json()["name"].rsplit("/", 1)[1]

    r = client.delete(
        f"/v1/users/user-1/weights/{weight_id}",
        headers={"X-Principal-Id": "coach-carol"},
    )
    assert r.status_code == 204, r.text

    repo = _weight_repo(fakes)
    assert repo.actor_log[-1] == ("archive", weight_id, "coach-carol")


def test_unattributed_request_records_anonymous_not_a_service_name(
    client, fakes
) -> None:
    """No principal header still names something truthful.

    ``get_principal`` never raises and degrades to ``anonymous`` (T-08-42).
    Recording that honestly is the point: the accepted risk is an un-named
    caller showing up as ``anonymous``, NOT as a fixed service name that looks
    like a real actor. Enforcing authentication is ``require_principal``'s job
    and is deliberately out of scope here.
    """
    r = client.post("/v1/users/user-1/weights", json={"weight": 180.5})
    assert r.status_code == 201, r.text

    repo = _weight_repo(fakes)
    assert repo.last_actor == "anonymous"
    assert repo.last_actor != "scheduler"
