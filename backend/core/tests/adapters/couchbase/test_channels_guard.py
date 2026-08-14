"""The Couchbase write path fails closed on access-destroying writes.

What the guard protects against: Sync Gateway derives read access from the
document body, so a write that clears a previously non-empty `channels`
array revokes that document for every subscriber except its owner. There is
no HTTP error and no signal on the affected devices — the document simply
disappears from participants' phones. `spring` is the only bucket, so a
regression here reaches every document type at once.

Why a null value and an empty list are refused identically: the production
sync function tests `if (doc.channels != null)` and concatenates. An empty
array passes that test but contributes nothing, so `combined` ends up as
`[doc.owner]` under either spelling. A future reader tempted to relax the
empty-list case needs that in front of them — permitting `[]` reopens the
exact hole this guard closes, under a different name.

One test per row of the decision table in
`specs/004-write-correctness/design.md`. Rejections assert two separate
things: that the error was raised, *and* that the fake driver recorded zero
write calls. The second is what proves the guard blocks the write rather
than merely complaining about it.

Fake-backed on purpose: these must stay runnable with no container and no
network.
"""

from __future__ import annotations

import logging

import pytest
from openwellness_core.adapters.couchbase.model.cb_participant_group import (
    CBParticipantGroup,
)
from openwellness_core.adapters.couchbase.model.cb_weight import CBWeight
from openwellness_core.adapters.couchbase.repositories.cb_base_repository import (
    CBBaseRepository,
)
from openwellness_core.adapters.exceptions import ChannelsInvariantError
from openwellness_core.domain.models.participant_group import ParticipantGroup
from openwellness_core.domain.models.weight import Weight

# The round-trip suite's fake is the one fake; recording is layered on top of
# it rather than reimplemented, so the two suites cannot drift apart.
from .test_channels_round_trip import (
    CHANNELS,
    REV,
    FakeEntityRepository,
    _group_doc,
    _weight_doc,
)


class RecordingEntityRepository(FakeEntityRepository):
    """The round-trip fake, plus a log of every write it was asked to do.

    The rejection tests assert against this log. "The exception was raised"
    and "nothing was written" are different claims, and only the second one
    is the property that matters to a participant's device.
    """

    def __init__(self) -> None:
        super().__init__()
        self.write_calls: list[tuple[str, dict]] = []

    def create(self, obj: dict) -> dict:
        self.write_calls.append(("create", dict(obj)))
        return super().create(obj)

    def update(self, doc_id: str, obj: dict) -> dict:
        self.write_calls.append(("update", dict(obj)))
        return super().update(doc_id, obj)

    def save(self, obj: dict) -> dict:
        self.write_calls.append(("save", dict(obj)))
        return super().save(obj)


@pytest.fixture()
def store() -> RecordingEntityRepository:
    return RecordingEntityRepository()


@pytest.fixture()
def weight_repo(
    store: RecordingEntityRepository,
) -> CBBaseRepository[Weight, CBWeight]:
    return CBBaseRepository(store, Weight, CBWeight)


@pytest.fixture()
def group_repo(
    store: RecordingEntityRepository,
) -> CBBaseRepository[ParticipantGroup, CBParticipantGroup]:
    return CBBaseRepository(store, ParticipantGroup, CBParticipantGroup)


def _unread_weight(**overrides) -> Weight:
    """A Weight built in memory, never loaded through the repository.

    It therefore carries no loaded-channels snapshot — the state the
    fail-closed row of the table is about.
    """
    kwargs = {
        "id": "w-1",
        "owner": "p1",
        "study_id": "s1",
        "weight": 180.5,
    }
    kwargs.update(overrides)
    return Weight(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Row 1: no prior revision — a create has no existing access to destroy
# ---------------------------------------------------------------------------


def test_entity_with_no_prior_revision_saves_with_null_channels(
    weight_repo, store
):
    """A never-persisted entity is never blocked, whatever its channels."""
    entity = _unread_weight(channels=None)
    assert entity._rev == ""

    weight_repo.save(entity)

    assert store.docs["w-1"]["channels"] is None
    assert len(store.write_calls) == 1


# ---------------------------------------------------------------------------
# Row 2: non-empty → different non-empty is an intentional change
# ---------------------------------------------------------------------------


def test_replacing_channels_with_a_different_non_empty_set_is_allowed(
    weight_repo, store
):
    """Changing who can read a document is not the failure mode guarded."""
    entity = weight_repo._from_doc(_weight_doc())
    assert entity.channels == CHANNELS

    entity.channels = ["study:s2", "cohort:c9", "role:coach"]
    weight_repo.save(entity)

    assert store.docs["w-1"]["channels"] == [
        "study:s2",
        "cohort:c9",
        "role:coach",
    ]


# ---------------------------------------------------------------------------
# Rows 3 & 4: clearing a non-empty prior set, under either spelling
# ---------------------------------------------------------------------------


def test_nulling_a_previously_non_empty_channel_set_is_rejected(weight_repo):
    """The original defect: read, write back, access silently revoked."""
    entity = weight_repo._from_doc(_weight_doc())
    entity.channels = None

    with pytest.raises(ChannelsInvariantError):
        weight_repo.save(entity)


def test_emptying_a_previously_non_empty_channel_set_is_rejected(weight_repo):
    """`[]` collapses access exactly as `None` does, so it is refused alike."""
    entity = weight_repo._from_doc(_weight_doc())
    entity.channels = []

    with pytest.raises(ChannelsInvariantError):
        weight_repo.save(entity)


def test_a_rejected_write_never_reaches_the_driver(weight_repo, store):
    """The claim that matters: no request was issued, so nothing applied."""
    entity = weight_repo._from_doc(_weight_doc())
    entity.channels = None

    with pytest.raises(ChannelsInvariantError):
        weight_repo.save(entity)

    assert store.write_calls == []


def test_a_rejected_empty_list_write_never_reaches_the_driver(
    weight_repo, store
):
    """Same proof for the empty-list spelling, which is the easier one to miss."""
    entity = weight_repo._from_doc(_weight_doc())
    entity.channels = []

    with pytest.raises(ChannelsInvariantError):
        weight_repo.save(entity)

    assert store.write_calls == []


def test_the_rejection_carries_the_structured_context_a_caller_needs(
    weight_repo,
):
    """Assert the attributes, not the message — wording is not the contract."""
    entity = weight_repo._from_doc(_weight_doc())
    entity.channels = []

    with pytest.raises(ChannelsInvariantError) as caught:
        weight_repo.save(entity)

    error = caught.value
    assert error.doc_id == "w-1"
    assert error.doc_type == "Weight"
    assert error.prior_channels == CHANNELS
    assert error.outgoing_channels == []


def test_the_rejection_emits_an_alertable_error_log(weight_repo, caplog):
    """A log-based alert rule keys on this record, so its content is contract."""
    entity = weight_repo._from_doc(_weight_doc())
    entity.channels = None

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ChannelsInvariantError):
            weight_repo.save(entity)

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "w-1" in message
    assert "Weight" in message
    assert str(CHANNELS) in message


# ---------------------------------------------------------------------------
# Row 5: there was no access to lose
# ---------------------------------------------------------------------------


def test_a_document_read_without_channels_may_be_saved_without_them(
    weight_repo, store
):
    """No prior channel set means no access for this write to destroy."""
    doc = _weight_doc()
    del doc["channels"]
    entity = weight_repo._from_doc(doc)
    assert entity.channels is None

    weight_repo.save(entity)

    assert store.docs["w-1"]["channels"] is None


def test_a_document_read_with_empty_channels_may_be_saved_empty(
    weight_repo, store
):
    """The empty-list spelling of the same "nothing to lose" state."""
    entity = weight_repo._from_doc(_weight_doc(channels=[]))
    assert entity.channels == []

    weight_repo.save(entity)

    assert store.docs["w-1"]["channels"] == []


# ---------------------------------------------------------------------------
# Rows 6 & 7: an entity that was never read back — unverifiable prior state
# ---------------------------------------------------------------------------


def test_an_unread_entity_with_a_prior_revision_cannot_clear_its_channels(
    weight_repo, store
):
    """Fail closed: a stored document exists whose channels are unknown here.

    This is precisely the defect shape the guard exists for — a caller
    hand-building an entity and writing it back. Permitting it because the
    prior state is unknown would make "fail closed" meaningless.
    """
    entity = _unread_weight(_rev=REV, channels=None)

    with pytest.raises(ChannelsInvariantError) as caught:
        weight_repo.save(entity)

    assert caught.value.doc_id == "w-1"
    assert caught.value.prior_channels is None
    assert store.write_calls == []


def test_an_unread_entity_may_still_set_a_non_empty_channel_list(
    weight_repo, store
):
    """Access is being granted, not destroyed, so there is nothing to protect."""
    entity = _unread_weight(_rev=REV, channels=["study:s1"])

    weight_repo.save(entity)

    assert store.docs["w-1"]["channels"] == ["study:s1"]


# ---------------------------------------------------------------------------
# The derived-channels write the guard must never break
# ---------------------------------------------------------------------------


def test_a_participant_group_round_trip_is_never_rejected(group_repo, store):
    """`CBParticipantGroup.from_domain` rewrites channels on every save.

    It is the most likely legitimate write for a careless guard to break, so
    it is asserted rather than assumed.
    """
    entity = group_repo._from_doc(_group_doc())

    group_repo.save(entity)

    assert store.docs["pg-1"]["channels"] == ["participantGroup:pg-1"]
    assert len(store.write_calls) == 1


def test_a_participant_group_with_nulled_channels_still_saves(
    group_repo, store
):
    """Even a caller clearing the field cannot destroy the derived channel.

    The persistence class re-derives it from the entity id at mapping time,
    so the outgoing array is non-empty and the guard has nothing to refuse.
    """
    entity = group_repo._from_doc(_group_doc())
    entity.channels = None

    group_repo.save(entity)

    assert store.docs["pg-1"]["channels"] == ["participantGroup:pg-1"]
