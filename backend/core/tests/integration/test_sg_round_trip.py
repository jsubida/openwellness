"""End-to-end proof that a read-modify-write through the Couchbase adapter
preserves document access, against a real Sync Gateway.

Skipped cleanly when the compose harness is absent (see `conftest.py` for the
gate and the command that starts it).

How this differs from `tests/adapters/couchbase/`: those suites are
fake-backed, and a fake cannot reproduce what this phase exists to prevent.
The defect's consequence is a *Sync Gateway* behavior — the sync function
derives channel membership from the document body, so a write that drops the
`channels` array silently revokes the document for every subscriber except its
owner and pushes that removal to their replicas. No exception is raised
anywhere. A fake asserting "the outgoing dict still had the array" measures
the adapter's output, and an admin read measures a interface that bypasses
channel authorization entirely; neither can distinguish a document that is
still shared from one that is not.

The measurement this file rests on is therefore
:func:`test_second_subscriber_keeps_access_across_the_round_trip`: a real Sync
Gateway user, subscribed to one of the document's channels and *not* its
owner, reading through the public interface. That read succeeding has exactly
one interpretation.

:func:`test_negative_control_subscriber_loses_access_when_channels_are_cleared`
is what makes the rest of the file mean anything. It deliberately reaches past
the repository guard to store a revision with no channels array and asserts
the same subscriber then loses access. Without it, a wholly green run would be
equally consistent with a Sync Gateway that never routed on channels at all,
and every other assertion here would be vacuous.

Seeding note: documents are seeded with ``repo.save()`` rather than
``repo.create()``. The driver's create path strips the id from the request
body, so Sync Gateway assigns its own — which would make
``CBParticipantGroup``'s derived ``participantGroup:{entity.id}`` channel
differ before and after the round trip, and the assertion below would be
measuring that id substitution instead of the round trip. ``save()`` on an
entity with an empty revision is the documented upsert path (see
``CBEntityRepository.update``) and PUTs at the entity's own id.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from openwellness_core.adapters.couchbase.model.cb_card import CBCard
from openwellness_core.adapters.couchbase.model.cb_participant_group import (
    CBParticipantGroup,
)
from openwellness_core.adapters.couchbase.model.cb_physical_activity import (
    CBPhysicalActivity,
)
from openwellness_core.adapters.couchbase.model.cb_weight import CBWeight
from openwellness_core.application.actors import is_system_actor, system_actor
from openwellness_core.domain.models.card import Card
from openwellness_core.domain.models.participant_group import ParticipantGroup
from openwellness_core.domain.models.physical_activity import PhysicalActivity
from openwellness_core.domain.models.weight import Weight

# Built through the helper so the value crossing a real Sync Gateway write is
# the same shape a real machine write carries.
ACTOR = system_actor("sg_round_trip")

# The owner is deliberately *not* the subscriber fixture's user: the sync
# function grants `doc.owner` unconditionally, so an owner's read would
# succeed even with the channels array destroyed.
OWNER = "participant-owner-not-the-subscriber"

# The field mutated mid-round-trip. Unrelated to channels and to the
# revision, so a change to it exercises the write path without touching what
# is being measured.
SEED_STUDY = "study-before"
MUTATED_STUDY = "study-after"

# Document types covered, chosen for the risk each represents (D-17):
#   ParticipantGroup — the only type whose persistence class *derives* its
#     channel value in `from_domain`; the legitimate write most likely to be
#     broken by the write guard
#   PhysicalActivity — high volume, and one of the two types a production
#     Sync Gateway webhook filters on, so its shape is externally observed
#   Weight           — exercises the `<Entity>Archived` archive convention
#   Card             — plain owner-scoped type with no special handling
# Adding a fifth type is one appended tuple.
COVERAGE: list[tuple[type, type, dict[str, Any]]] = [
    (ParticipantGroup, CBParticipantGroup, {"participant_ids": ["p1"], "pid_to_mid": {}}),
    (PhysicalActivity, CBPhysicalActivity, {"activity_id": "a1", "name": "Walk", "item_description": "brisk", "minutes": 30, "intensity": 2, "date_of_activity": 1700000000.0, "enjoyment": 4, "met": 3.5}),
    (Weight, CBWeight, {"weight": 180.5}),
    (Card, CBCard, {"title": "t", "description": "d", "url": "https://example.invalid"}),
]

COVERAGE_IDS = [entity_cls.__name__ for entity_cls, _, _ in COVERAGE]


def _build(entity_cls: type, extra: dict[str, Any], channel: str) -> Any:
    """Construct a domain entity carrying an owner and one channel."""
    return entity_cls(
        owner=OWNER, study_id=SEED_STUDY, channels=[channel], **extra
    )


def _last_seq(sg_harness) -> Any:
    """Current Sync Gateway sequence, for bounding a later `_changes` read."""
    response = requests.get(f"{sg_harness.admin_db_url}/_changes", timeout=15)
    assert response.status_code == 200, response.text
    return response.json()["last_seq"]


def _ids_changed_since(sg_harness, since: Any) -> list[str]:
    """Document ids Sync Gateway has seen since `since`.

    The archive path stores a *new* document under a server-assigned id and
    the repository returns nothing, so the changes feed is the only way to
    name the archive copy without a N1QL index.
    """
    response = requests.get(
        f"{sg_harness.admin_db_url}/_changes?since={since}", timeout=15
    )
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()["results"]]


@pytest.mark.parametrize(
    "entity_cls,persistence_cls,extra", COVERAGE, ids=COVERAGE_IDS
)
def test_round_trip_preserves_channels_and_advances_the_revision(
    entity_cls,
    persistence_cls,
    extra,
    repo_factory,
    sg_subscriber,
    sg_documents,
    admin_read,
):
    """Read, modify, write back — and the document is still what it was."""
    repo = repo_factory(entity_cls, persistence_cls)
    entity = _build(entity_cls, extra, sg_subscriber.channel)
    # Registered before the write, so a failed assertion still cleans up.
    sg_documents(entity.id)

    seeded = repo.save(entity, actor=ACTOR)
    assert seeded.id == entity.id
    seeded_channels = seeded.channels
    assert seeded_channels, "the seed must carry a non-empty channels array"
    seeded_rev = seeded._rev
    assert seeded_rev, "Sync Gateway must return a revision for the seed write"

    reread = repo.get_by_id(seeded.id)
    assert reread is not None
    # The read path carries both fields onto the domain entity. Before 08-04
    # `valid_fields()` dropped them here, which is where the whole defect
    # started: the next write then sent no channels and an empty revision.
    assert reread.channels == seeded_channels
    assert reread._rev == seeded_rev
    assert reread._rev != "", "the revision must be populated, not empty"

    reread.study_id = MUTATED_STUDY
    saved = repo.save(reread, actor=ACTOR)
    assert saved.channels == seeded_channels
    # Compared against the revision the seed returned, not merely asserted
    # non-empty: a non-empty revision that never moved is exactly the
    # pre-fix behavior, where every write went out with an empty `?rev=`.
    assert saved._rev != seeded_rev

    stored = admin_read(seeded.id)
    assert stored.status_code == 200
    body = stored.json()
    assert body["channels"] == seeded_channels
    assert body["studyId"] == MUTATED_STUDY
    assert body["_rev"] == saved._rev
    # DATA-04 against the real store: the actor the write named, in the
    # machine-actor form, not the driver's own service name.
    assert body["updatedBy"] == ACTOR
    assert is_system_actor(body["updatedBy"])


def test_participant_group_keeps_its_derived_routing_channel(
    repo_factory, sg_documents, admin_read
):
    """The one type whose channel is derived, not supplied.

    `CBParticipantGroup.from_domain` recomputes `participantGroup:{id}` on
    every write. That is a legitimate rewrite of a non-empty array, so the
    guard must let it through — and the round trip must end with the derived
    channel still present rather than overwritten by a stale value.
    """
    repo = repo_factory(ParticipantGroup, CBParticipantGroup)
    group = ParticipantGroup(
        owner=OWNER, study_id=SEED_STUDY, participant_ids=["p1"], pid_to_mid={}
    )
    sg_documents(group.id)

    seeded = repo.save(group, actor=ACTOR)
    derived = f"participantGroup:{group.id}"
    assert seeded.channels == [derived]

    reread = repo.get_by_id(seeded.id)
    assert reread is not None
    reread.info = {"note": "round-tripped"}
    saved = repo.save(reread, actor=ACTOR)
    assert saved.channels == [derived]

    body = admin_read(seeded.id).json()
    assert body["channels"] == [derived]


def test_weight_archive_carries_the_archived_type_discriminator(
    sg_harness, repo_factory, sg_subscriber, sg_documents, admin_read
):
    """Archiving writes a second document under the archived discriminator."""
    repo = repo_factory(Weight, CBWeight)
    weight = Weight(
        owner=OWNER,
        study_id=SEED_STUDY,
        weight=180.5,
        channels=[sg_subscriber.channel],
    )
    sg_documents(weight.id)
    repo.save(weight, actor=ACTOR)

    before = _last_seq(sg_harness)
    repo.archive(weight.id, actor=ACTOR)
    new_ids = [i for i in _ids_changed_since(sg_harness, before) if i != weight.id]
    assert len(new_ids) == 1, f"expected exactly one archive copy, got {new_ids}"
    for doc_id in new_ids:
        sg_documents(doc_id)

    archived = admin_read(new_ids[0])
    assert archived.status_code == 200
    body = archived.json()
    assert body["type"] == f"{CBWeight.type}Archived"
    # The archive copy keeps the original's access, so archiving does not
    # quietly remove the record from the participants who could read it.
    assert body["channels"] == [sg_subscriber.channel]
    assert body["updatedBy"] == ACTOR

    # The original is untouched by archiving.
    original = admin_read(weight.id)
    assert original.status_code == 200
    assert original.json()["type"] == CBWeight.type


def test_second_subscriber_keeps_access_across_the_round_trip(
    repo_factory, sg_subscriber, sg_documents, read_as_user, admin_read
):
    """The centerpiece: a non-owner subscriber still sees the document.

    Three observations, each with a single interpretation — the subscriber
    can read it before the round trip, the round trip happens, the subscriber
    can still read it. Checking access *before* is not ceremony: without it a
    later failure would be ambiguous between "the round trip broke it" and
    "this user never had access in the first place".
    """
    repo = repo_factory(Card, CBCard)
    card = Card(
        owner=OWNER,
        study_id=SEED_STUDY,
        title="t",
        description="d",
        url="https://example.invalid",
        channels=[sg_subscriber.channel],
    )
    sg_documents(card.id)
    seeded = repo.save(card, actor=ACTOR)
    assert seeded.channels == [sg_subscriber.channel]

    before = read_as_user(sg_subscriber, card.id)
    assert before.status_code == 200, (
        "the subscriber must be able to read the document before the round "
        f"trip, or the measurement is meaningless; got {before.status_code}"
    )

    reread = repo.get_by_id(card.id)
    assert reread is not None
    reread.title = "t (edited)"
    saved = repo.save(reread, actor=ACTOR)
    assert saved._rev != seeded._rev

    after = read_as_user(sg_subscriber, card.id)
    assert after.status_code == 200, (
        "the subscriber lost access across a read-modify-write — this is the "
        f"defect this phase exists to prevent; got {after.status_code}"
    )
    assert after.json()["title"] == "t (edited)"

    # Secondary, and only ever secondary: the admin interface bypasses
    # channel authorization, so this could not have proven the read above.
    assert admin_read(card.id).json()["channels"] == [sg_subscriber.channel]


def test_negative_control_subscriber_loses_access_when_channels_are_cleared(
    cb_driver, repo_factory, sg_subscriber, sg_documents, read_as_user, admin_read
):
    """Prove the harness can actually detect the failure it claims to rule out.

    This test DELIBERATELY BYPASSES the repository guard, writing through the
    driver with a body that carries no `channels` key at all. That is exactly
    the write `CBBaseRepository.save` refuses, and going around it is the
    point: if clearing the array did *not* cost the subscriber access, the
    sync function would not be routing on channels, and every assertion in
    this file — including the one above it — would pass vacuously.

    Nothing outside this test may write through the driver directly.
    """
    repo = repo_factory(Card, CBCard)
    card = Card(
        owner=OWNER,
        study_id=SEED_STUDY,
        title="t",
        description="d",
        url="https://example.invalid",
        channels=[sg_subscriber.channel],
    )
    sg_documents(card.id)
    repo.save(card, actor=ACTOR)

    before = read_as_user(sg_subscriber, card.id)
    assert before.status_code == 200, (
        "the control starts from the same visible state as the positive "
        f"case; got {before.status_code}"
    )

    stored = admin_read(card.id).json()
    bypass = {k: v for k, v in stored.items() if k not in ("_id", "channels")}
    bypass["_rev"] = stored["_rev"]
    assert "channels" not in bypass
    cb_driver.update(card.id, bypass, actor=ACTOR)

    # The document is still there — this is a loss of access, not a deletion,
    # which is precisely why it is invisible to the writer.
    surviving = admin_read(card.id)
    assert surviving.status_code == 200
    assert not surviving.json().get("channels")

    after = read_as_user(sg_subscriber, card.id)
    # Sync Gateway 2.8.2 answers 403 on this path; a 404 is the same answer
    # on others and in later versions. Both mean "this user cannot see it",
    # and accepting either keeps the control measuring access rather than a
    # status-code convention.
    assert after.status_code in (403, 404), (
        "the subscriber still reads the document after its channels were "
        "cleared, so this harness cannot detect the failure the rest of this "
        f"file claims to rule out; got {after.status_code}"
    )
