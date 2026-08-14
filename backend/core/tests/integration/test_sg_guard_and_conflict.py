"""End-to-end proof of the two *failure* paths, against a real Sync Gateway.

`test_sg_round_trip.py` proves the success path — a read-modify-write keeps a
document readable. This module proves the two rejections, and it proves them by
their *outcome in the store* rather than by the exception alone:

* **The guard (D-19, DATA-02).** 08-05 already proves `CBBaseRepository.save`
  raises `ChannelsInvariantError` for an access-destroying write, using a fake
  driver. That proves the code path, not the outcome. ROADMAP §Phase 8 success
  criterion 2 says the stored document must be *observably unchanged*, and an
  observation needs something to observe. So every rejection case here captures
  the entire document body through Sync Gateway before the attempt and compares
  the entire body — revision included — afterward. A guard that raised *after*
  partially writing would advance the revision and fail that compare; an
  exception-only assertion would not notice.

The stale-revision conflict case (D-21) and the attribution assertions land in
this same module next.

**Nothing is excluded from the document compare.** Sync Gateway 2.8.2's admin
`GET /{db}/{doc}` returns the stored body plus `_id` and `_rev` only — the
`_sync` metadata envelope lives in the Couchbase document, not in the REST
representation, and is not surfaced here. :data:`EXCLUDED_FROM_COMPARE` is
therefore empty, and :func:`_capture` asserts the envelope really is absent
rather than trusting that note to stay true. Excluding a key because a compare
failed on it is how a real regression gets normalized away (T-08-56); if a
future Sync Gateway starts surfacing `_sync`, this file should fail loudly and
be amended deliberately.

Seeding follows the same convention as the round-trip module: `repo.save()`,
never `repo.create()`. The driver's create path strips the id so Sync Gateway
assigns its own, which would make every document id here unpredictable.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

import pytest

from openwellness_core.adapters.couchbase.model.cb_card import CBCard
from openwellness_core.adapters.exceptions import ChannelsInvariantError
from openwellness_core.application.actors import system_actor
from openwellness_core.domain.models.card import Card

# Built through the helper, so the value crossing a real write is the shape a
# real machine write carries.
ACTOR = system_actor("sg_guard_and_conflict")

# The owner is deliberately *not* the subscriber fixture's user: the sync
# function grants `doc.owner` unconditionally, so an owner's read would succeed
# even with the channels array destroyed.
OWNER = "participant-owner-not-the-subscriber"

SEED_STUDY = "study-guard-and-conflict"

# Keys removed from the full-document compare. Empty on purpose — see the
# module docstring. Every future entry needs a one-line reason beside it
# explaining why Sync Gateway is entitled to change that key between two reads
# of an unmodified document.
EXCLUDED_FROM_COMPARE: frozenset[str] = frozenset()

# Both spellings of "destroy this document's access". D-12 makes them
# equivalent: the production sync function tests `if (doc.channels != null)`,
# which an empty array passes while contributing no channels, so the combined
# set collapses to `[doc.owner]` either way. Parameterized rather than run
# sequentially so a failure names which spelling broke.
DESTROYING_VALUES: list[list[str] | None] = [None, []]
DESTROYING_IDS = ["null", "empty-list"]


def _new_channel() -> str:
    """A channel name no other test in this session will collide with."""
    return f"itest:{uuid.uuid4().hex[:12]}"


def _card(channels: list[str], **overrides: Any) -> Card:
    """A Card carrying an owner and an explicit channels array."""
    fields: dict[str, Any] = {
        "owner": OWNER,
        "study_id": SEED_STUDY,
        "title": "seed title",
        "description": "seed description",
        "url": "https://example.invalid",
        "channels": channels,
    }
    fields.update(overrides)
    return Card(**fields)


def _capture(admin_read: Callable[[str], Any], doc_id: str) -> dict[str, Any]:
    """The whole stored document, as Sync Gateway returns it.

    Asserts the metadata envelope is absent so :data:`EXCLUDED_FROM_COMPARE`
    being empty is a checked fact rather than a comment.
    """
    response = admin_read(doc_id)
    assert response.status_code == 200, (
        f"could not read {doc_id} back through Sync Gateway: "
        f"{response.status_code} {response.text}"
    )
    body = response.json()
    assert "_sync" not in body, (
        "Sync Gateway now surfaces the `_sync` envelope on an admin read. The "
        "compare in this module excludes nothing; decide deliberately whether "
        "this key belongs in EXCLUDED_FROM_COMPARE rather than dropping it to "
        "make a failure go away."
    )
    return {k: v for k, v in body.items() if k not in EXCLUDED_FROM_COMPARE}


# ---------------------------------------------------------------------------
# D-19 — the rejected write leaves the stored document identical
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "destroying_value", DESTROYING_VALUES, ids=DESTROYING_IDS
)
def test_rejected_write_leaves_the_stored_document_identical(
    destroying_value,
    repo_factory,
    sg_subscriber,
    sg_documents,
    read_as_user,
    admin_read,
):
    """Attempt the access-destroying write; the store must not move at all."""
    repo = repo_factory(Card, CBCard)
    card = _card([sg_subscriber.channel])
    # Registered before the write, so a failed assertion still cleans up.
    sg_documents(card.id)

    seeded = repo.save(card, actor=ACTOR)
    assert seeded.channels == [sg_subscriber.channel]
    assert seeded._rev, "Sync Gateway must return a revision for the seed write"

    # Baseline: the subscriber can see it now. Without this a later 403 would
    # be ambiguous between "the attempt broke access" and "this user never had
    # access in the first place".
    before_read = read_as_user(sg_subscriber, card.id)
    assert before_read.status_code == 200, (
        "the subscriber must be able to read the document before the rejected "
        f"attempt, or the measurement is meaningless; got {before_read.status_code}"
    )

    captured = _capture(admin_read, card.id)
    assert captured["channels"] == [sg_subscriber.channel]
    assert captured["_rev"] == seeded._rev

    # Loaded through the repository, so the guard has a channels snapshot to
    # compare against — the intended usage, not the unverifiable-prior path.
    entity = repo.get_by_id(card.id)
    assert entity is not None
    assert entity.channels == [sg_subscriber.channel]
    entity.channels = destroying_value

    with pytest.raises(ChannelsInvariantError) as raised:
        repo.save(entity, actor=ACTOR)

    # Structured attributes, never the message text: the message is a log
    # format that may be reworded, the attributes are the contract.
    error = raised.value
    assert error.doc_id == card.id
    assert error.doc_type == CBCard.type
    assert error.prior_channels == [sg_subscriber.channel]
    assert error.outgoing_channels == destroying_value

    # The whole point. Not `body["channels"]` — a partial read cannot rule out
    # that some other part of the document was written before the guard fired,
    # and the revision is what would betray a partial write.
    after = _capture(admin_read, card.id)
    assert after == captured, (
        "the stored document changed across a rejected write; ROADMAP §Phase 8 "
        "criterion 2 requires it to be observably unchanged"
    )

    # The participant-visible statement of "observably unchanged", and the one
    # an operator would recognize.
    after_read = read_as_user(sg_subscriber, card.id)
    assert after_read.status_code == 200, (
        "the subscriber lost access across a write that was supposed to have "
        f"been rejected outright; got {after_read.status_code}"
    )
    assert after_read.json()["title"] == "seed title"


def test_a_legitimate_channel_change_still_reaches_the_store(
    repo_factory, sg_subscriber, sg_documents, read_as_user, admin_read
):
    """The guard must not be a blanket ban on changing `channels`.

    Without this, a guard that rejected *every* channels change would satisfy
    every other assertion in this file while taking production writes down
    entirely (T-08-57). Two allowed shapes are exercised: widening an array
    the subscriber is in, and reassigning to a disjoint array — a deliberate
    relocation of access, which is a legitimate operation and not the silent
    revocation the guard exists to stop.
    """
    repo = repo_factory(Card, CBCard)
    relocated = _new_channel()
    card = _card([sg_subscriber.channel])
    sg_documents(card.id)

    seeded = repo.save(card, actor=ACTOR)
    assert read_as_user(sg_subscriber, card.id).status_code == 200

    # 1. Widen: a different non-empty array that still includes the subscriber.
    widened = repo.get_by_id(card.id)
    assert widened is not None
    widened.channels = [sg_subscriber.channel, relocated]
    saved = repo.save(widened, actor=ACTOR)
    assert saved.channels == [sg_subscriber.channel, relocated]
    assert saved._rev != seeded._rev, "the allowed change must advance the revision"
    assert _capture(admin_read, card.id)["channels"] == [
        sg_subscriber.channel,
        relocated,
    ]
    assert read_as_user(sg_subscriber, card.id).status_code == 200

    # 2. Reassign to a disjoint non-empty array. Allowed: access is being
    #    moved, not removed. The subscriber losing it here is the intended
    #    result of the caller's own instruction, not a silent side effect.
    moved = repo.get_by_id(card.id)
    assert moved is not None
    moved.channels = [relocated]
    repo.save(moved, actor=ACTOR)
    assert _capture(admin_read, card.id)["channels"] == [relocated]
