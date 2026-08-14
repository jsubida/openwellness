"""The Couchbase persistence boundary round-trips access metadata losslessly.

The defect these tests guard against (`specs/004-write-correctness/`):
`CBBaseEntity.to_domain` keeps only the keys present in
`entity_cls.valid_fields()`, and the domain `BaseEntity` used to declare just
`id`. `channels` and `_rev` were therefore dropped on every read and came back
as `None`/`""` on the next write. Through the production Sync Gateway sync
function an emptied `channels` array collapses document access to
`[doc.owner]` — every other subscriber silently loses the document on their
device, with no HTTP error anywhere. A dropped `_rev` additionally means
updates are sent unversioned, so Sync Gateway cannot enforce optimistic
concurrency.

The fix is narrow: declaring both fields on the domain `BaseEntity` is enough,
because the same `valid_fields()` set governs both filter sites. These tests
assert *both* sites — `CBBaseEntity.to_domain` (via `_from_doc`) and
`CBBaseRepository.update_entity_valid_fields`, which is an independent second
copy of the same filter in a different file and is the one a future refactor is
most likely to miss.

This suite is fake-backed on purpose. The proof against a real Sync Gateway
lives in the integration suite; these tests must stay runnable with no
container and no network.
"""

from __future__ import annotations

from typing import Optional

import pytest
from openwellness_core.adapters.couchbase.model.cb_participant_group import (
    CBParticipantGroup,
)
from openwellness_core.adapters.couchbase.model.cb_weight import CBWeight
from openwellness_core.adapters.couchbase.repositories.cb_base_repository import (
    CBBaseRepository,
)
from openwellness_core.adapters.interfaces.entity_repository import (
    EntityRepository,
)
from openwellness_core.application.actors import system_actor
from openwellness_core.domain.models.participant_group import ParticipantGroup
from openwellness_core.domain.models.weight import Weight

BUCKET = "spring"

# Actors are built through the helper rather than spelled inline, so the test
# corpus demonstrates the intended shape and a grep for the bare namespace
# prefix in tests finds nothing. Two values, because "the write recorded the
# actor" is only meaningful if it differs from what the document arrived
# carrying (`updatedBy: p1` in `_weight_doc`) and from the seeding write.
ACTOR = system_actor("channels_round_trip")
SEED_ACTOR = system_actor("channels_round_trip_seed")

# Shaped like a real Sync Gateway revision id (generation-hash), not a
# placeholder, so a formatting assumption can't hide behind a short string.
REV = "3-9f2c1a4b7e0d5c68a1b3f4e2d7c9b0a5"

CHANNELS = ["participantGroup:pg-1", "study:s1"]


class FakeEntityRepository(EntityRepository):
    """In-memory document store keyed by document id.

    Deliberately dumb: it stores and returns whatever dict it is handed, so
    anything lost in a round trip was lost by the adapter, not by the store.
    """

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    @property
    def bucket(self) -> str:
        return BUCKET

    def get_by_id(self, doc_id: str) -> Optional[dict]:
        stored = self.docs.get(doc_id)
        return dict(stored) if stored is not None else None

    def get_by_query(
        self, query: str, params: Optional[dict] = None
    ) -> list[dict]:
        return [dict(doc) for doc in self.docs.values()]

    # `actor` is accepted and deliberately not applied to the stored dict.
    # This fake exists to prove `channels`/`_rev` survive a round trip;
    # stamping the audit field here would duplicate the driver's job and
    # make the store no longer "returns whatever it was handed". Actor
    # stamping is proven against the real driver in
    # `tests/infrastructure/drivers/test_cb_entity_repository.py`.
    def create(self, obj: dict, *, actor: str) -> dict:
        self.docs[obj["id"]] = dict(obj)
        return dict(obj)

    def update(self, doc_id: str, obj: dict, *, actor: str) -> dict:
        self.docs[doc_id] = dict(obj)
        return dict(obj)

    def save(self, obj: dict, *, actor: str) -> dict:
        self.docs[obj["id"]] = dict(obj)
        return dict(obj)

    def delete(self, doc_id: str) -> dict | None:
        return self.docs.pop(doc_id, None)


class StampingEntityRepository(FakeEntityRepository):
    """The same store, plus the one thing the real driver does to a document.

    `CBEntityRepository.create`/`.update` assign `obj["updatedBy"] = actor`
    before sending the body. Reproducing exactly that — and nothing else —
    lets the repository-level suite assert on a stored document body without
    the base fake losing its "returns whatever it was handed" property, which
    the channels assertions depend on.
    """

    def create(self, obj: dict, *, actor: str) -> dict:
        return super().create({**obj, "updatedBy": actor}, actor=actor)

    def update(self, doc_id: str, obj: dict, *, actor: str) -> dict:
        return super().update(doc_id, {**obj, "updatedBy": actor}, actor=actor)

    def save(self, obj: dict, *, actor: str) -> dict:
        return super().save({**obj, "updatedBy": actor}, actor=actor)


@pytest.fixture()
def store() -> FakeEntityRepository:
    return FakeEntityRepository()


@pytest.fixture()
def stamping_store() -> StampingEntityRepository:
    return StampingEntityRepository()


@pytest.fixture()
def stamping_weight_repo(
    stamping_store: StampingEntityRepository,
) -> CBBaseRepository[Weight, CBWeight]:
    return CBBaseRepository(stamping_store, Weight, CBWeight)


@pytest.fixture()
def weight_repo(
    store: FakeEntityRepository,
) -> CBBaseRepository[Weight, CBWeight]:
    return CBBaseRepository(store, Weight, CBWeight)


@pytest.fixture()
def group_repo(
    store: FakeEntityRepository,
) -> CBBaseRepository[ParticipantGroup, CBParticipantGroup]:
    return CBBaseRepository(store, ParticipantGroup, CBParticipantGroup)


def _weight_doc(**overrides) -> dict:
    """A wire-format Weight document as Sync Gateway would hand it back."""
    doc = {
        "id": "w-1",
        "_rev": REV,
        "channels": list(CHANNELS),
        "type": "Weight",
        "owner": "p1",
        "studyId": "s1",
        "updatedBy": "p1",
        "createdAt": 1700000000.0,
        "updatedAt": 1700000100.0,
        "createdAtTzOffset": -21600,
        "updatedAtTzOffset": -21600,
        "weight": 180.5,
    }
    doc.update(overrides)
    return doc


def _group_doc(**overrides) -> dict:
    """A wire-format ParticipantGroup document (the channel-deriving type)."""
    doc = {
        "id": "pg-1",
        "_rev": REV,
        "channels": ["participantGroup:pg-1"],
        "type": "ParticipantGroup",
        "owner": "p1",
        "studyId": "s1",
        "updatedBy": "p1",
        "createdAt": 1700000000.0,
        "updatedAt": 1700000100.0,
        "createdAtTzOffset": 0,
        "updatedAtTzOffset": 0,
        "participantIds": ["a", "b"],
        "pidToMid": {"a": "m1"},
        "info": {},
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# Document → entity (CBBaseEntity.to_domain, filter site 1)
# ---------------------------------------------------------------------------


def test_from_doc_carries_channels_and_rev_onto_the_entity(weight_repo):
    """Reading a document must not drop its access metadata or revision."""
    entity = weight_repo._from_doc(_weight_doc())

    assert entity.channels == CHANNELS
    assert entity._rev == REV


def test_from_doc_carries_channels_and_rev_for_a_second_entity_type(
    group_repo,
):
    """The fix is on the shared base, so it holds for every entity type."""
    entity = group_repo._from_doc(_group_doc())

    assert entity.channels == ["participantGroup:pg-1"]
    assert entity._rev == REV
    assert entity.participant_ids == ["a", "b"]


# ---------------------------------------------------------------------------
# Entity → document (CBBaseEntity.from_domain / model_dump)
# ---------------------------------------------------------------------------


def test_to_doc_emits_the_channels_it_was_read_with(weight_repo):
    """Writing back an unmodified entity must reproduce the same array."""
    entity = weight_repo._from_doc(_weight_doc())

    doc = weight_repo._to_doc(entity)

    assert doc["channels"] == CHANNELS


def test_to_doc_aliases_the_revision_to_the_wire_field_name(weight_repo):
    """The driver sends `_rev`; the domain field is `_rev` too, via the alias."""
    entity = weight_repo._from_doc(_weight_doc())

    doc = weight_repo._to_doc(entity)

    assert doc["_rev"] == REV
    assert "rev" not in doc


def test_full_round_trip_through_the_store_preserves_both_fields(
    weight_repo, store
):
    """document → entity → document → entity, with a save in the middle."""
    store.create(_weight_doc(), actor=SEED_ACTOR)

    entity = weight_repo.get_by_id("w-1")
    assert entity is not None
    saved = weight_repo.save(entity, actor=ACTOR)

    assert store.docs["w-1"]["channels"] == CHANNELS
    assert store.docs["w-1"]["_rev"] == REV
    assert saved.channels == CHANNELS
    assert saved._rev == REV


# ---------------------------------------------------------------------------
# The actor reaches the document body (repository half of the proof)
# ---------------------------------------------------------------------------


def test_a_save_writes_the_actor_argument_into_the_document(
    stamping_weight_repo, stamping_store
):
    """The counterpart to the driver-level actor test.

    `tests/infrastructure/drivers/test_cb_entity_repository.py` proves the
    driver stamps the actor it is given; this proves the repository gives it
    the actor its own caller supplied. Neither test alone establishes that a
    value survives from call site to document body — the seam between them is
    exactly where 08-06's interim bridge silently substituted the entity's
    own `updatedBy` instead.
    """
    stamping_store.create(_weight_doc(), actor=SEED_ACTOR)
    entity = stamping_weight_repo.get_by_id("w-1")
    assert entity is not None
    # The entity knows who wrote it *last*, which is not who is writing it
    # now. Deriving the actor from this value is the defect being removed.
    assert entity.updated_by == SEED_ACTOR

    stamping_weight_repo.save(entity, actor=ACTOR)

    assert stamping_store.docs["w-1"]["updatedBy"] == ACTOR


def test_an_archive_attributes_the_copy_to_the_archiving_actor(
    stamping_weight_repo, stamping_store
):
    """Archiving writes a new document, so it names who archived it.

    The entity is re-read inside `archive()`, which makes it the easiest
    place to fall back on the stored `updatedBy` — the exact substitution
    this plan removes.
    """
    stamping_store.create(_weight_doc(), actor=SEED_ACTOR)

    stamping_weight_repo.archive("w-1", actor=ACTOR)

    # The archive copy keeps the entity id and changes only its `type`, and
    # this fake keys documents by id — so the archived body is what is stored
    # under "w-1" after the call.
    archived = stamping_store.docs["w-1"]
    assert archived["type"] == "WeightArchived"
    assert archived["updatedBy"] == ACTOR


# ---------------------------------------------------------------------------
# In-place field application (update_entity_valid_fields, filter site 2)
# ---------------------------------------------------------------------------


def test_update_entity_valid_fields_applies_channels_and_rev(weight_repo):
    """The second, independent copy of the `valid_fields()` filter.

    Several repositories rehydrate an existing entity from a wire dict rather
    than constructing a fresh one; that path filters through the same set and
    would otherwise discard the same two fields.
    """
    entity = Weight(id="w-1", owner="p1", study_id="s1", weight=180.5)
    assert entity.channels is None
    assert entity._rev == ""

    updated = weight_repo.update_entity_valid_fields(entity, _weight_doc())

    assert updated.channels == CHANNELS
    assert updated._rev == REV
    assert updated is entity


# ---------------------------------------------------------------------------
# Channel derivation must still win where a subclass defines it
# ---------------------------------------------------------------------------


def test_participant_group_derives_its_channel_on_write(group_repo):
    """`CBParticipantGroup.from_domain` overrides channels; that must be what ships."""
    entity = group_repo._from_doc(
        _group_doc(channels=["participantGroup:stale"])
    )

    doc = group_repo._to_doc(entity)

    assert doc["channels"] == ["participantGroup:pg-1"]
    assert doc["_rev"] == REV


# ---------------------------------------------------------------------------
# None and [] must stay distinguishable
# ---------------------------------------------------------------------------


def test_absent_channels_reads_back_as_none(weight_repo):
    """A document that never carried channels yields `None`, not `[]`."""
    doc = _weight_doc()
    del doc["channels"]

    entity = weight_repo._from_doc(doc)

    assert entity.channels is None


def test_empty_channels_reads_back_as_empty_list(weight_repo):
    """An explicitly emptied array yields `[]`, not `None`.

    The write guard treats "never had channels" and "channels being cleared"
    differently, so collapsing the two here would defeat it.
    """
    entity = weight_repo._from_doc(_weight_doc(channels=[]))

    assert entity.channels == []
    assert entity.channels is not None
