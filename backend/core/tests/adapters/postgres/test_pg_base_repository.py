"""PGBaseRepository CRUD/archive behavior, backed by an in-memory SQLite engine.

SQLite stands in for Postgres here (see `pg_base_entity.py`'s JSON/JSONB
variant): it supports enough of the shared shape (TEXT/JSON columns) to
exercise the repository logic without a real Postgres instance, mirroring
how the Mongo/Couchbase base-repository tests use in-memory fakes.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import and_, create_engine
from sqlalchemy.orm import sessionmaker

from openwellness_core.adapters.postgres.model.pg_base_entity import (
    Base,
    PGBaseEntity,
)
from openwellness_core.adapters.postgres.repositories.pg_base_repository import (
    PGBaseRepository,
)
from openwellness_core.application.actors import system_actor
from openwellness_core.domain.exceptions.domain_exception import (
    EntityNotFoundException,
)
from openwellness_core.domain.models.weight import Weight

# Every write in this module names an actor, built through the helper rather
# than spelled inline. Two distinct values: `ACTOR` performs the writes under
# test, `SEED_ACTOR` performs the setup writes, so an assertion that the
# stored attribution changed cannot pass by accident.
ACTOR = system_actor("pg_repository_test")
SEED_ACTOR = system_actor("pg_repository_seed")


class PGTestWeight(PGBaseEntity, Base):
    __tablename__ = "test_pg_base_repository_weights"


class PGTestWeightArchive(PGBaseEntity, Base):
    __tablename__ = "test_pg_base_repository_weights_archive"


@pytest.fixture()
def repo() -> PGBaseRepository[Weight, PGTestWeight]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return PGBaseRepository(
        session_factory=session_factory,
        entity_type=Weight,
        persistence_type=PGTestWeight,
        archive_persistence_type=PGTestWeightArchive,
    )


def _weight(
    *, id: str | None = None, owner: str = "p1", created_at: float | None = None
) -> Weight:
    kwargs: dict = {"owner": owner, "study_id": "s1", "weight": 180.5}
    if id is not None:
        kwargs["id"] = id
    if created_at is not None:
        kwargs["created_at"] = created_at
    return Weight(**kwargs)


def test_create_and_get_by_id(repo):
    w = _weight()

    created = repo.create(w, actor=ACTOR)

    assert created.id == w.id
    fetched = repo.get_by_id(w.id)
    assert fetched is not None
    assert fetched.id == w.id
    assert fetched.owner == "p1"
    assert fetched.weight == 180.5


def test_get_by_id_missing_returns_none(repo):
    assert repo.get_by_id("does-not-exist") is None


def test_save_with_no_id_inserts(repo):
    w = _weight(id="")

    saved = repo.save(w, actor=ACTOR)

    assert saved.id
    assert repo.get_by_id(saved.id) is not None


def test_save_with_existing_id_updates_and_increments_revision(repo):
    w = _weight()
    repo.create(w, actor=SEED_ACTOR)

    w.weight = 190.0
    repo.save(w, actor=ACTOR)
    w.weight = 200.0
    repo.save(w, actor=ACTOR)

    fetched = repo.get_by_id(w.id)
    assert fetched.weight == 200.0
    with repo.session_factory() as session:
        row = session.get(PGTestWeight, w.id)
        assert row.revision == 2


def test_delete(repo):
    w = _weight()
    repo.create(w, actor=SEED_ACTOR)

    result = repo.delete(w.id)

    assert result == w.id
    assert repo.get_by_id(w.id) is None


def test_delete_missing_returns_none(repo):
    assert repo.delete("does-not-exist") is None


def test_list_all(repo):
    repo.create(_weight(), actor=SEED_ACTOR)
    repo.create(_weight(), actor=SEED_ACTOR)

    assert len(repo.list_all()) == 2


def test_get_by_query_range_filter(repo):
    old = _weight(owner="p1", created_at=1_000_000.0)
    recent = _weight(owner="p1", created_at=2_000_000.0)
    other_owner = _weight(owner="p2", created_at=1_500_000.0)
    repo.create(old, actor=SEED_ACTOR)
    repo.create(recent, actor=SEED_ACTOR)
    repo.create(other_owner, actor=SEED_ACTOR)

    start = datetime.fromtimestamp(1_200_000.0, tz=timezone.utc)
    end = datetime.fromtimestamp(2_500_000.0, tz=timezone.utc)
    query = and_(
        PGTestWeight.owner == "p1",
        PGTestWeight.created_at.between(start, end),
    )

    results = repo.get_by_query(query)

    assert [r.id for r in results] == [recent.id]


def test_archive_copies_row_and_leaves_original(repo):
    w = _weight()
    repo.create(w, actor=SEED_ACTOR)

    repo.archive(w.id, actor=ACTOR)

    assert repo.get_by_id(w.id) is not None
    with repo.session_factory() as session:
        archived = session.get(PGTestWeightArchive, w.id)
        assert archived is not None
        assert archived.data["weight"] == 180.5


def test_archive_missing_raises():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    repo = PGBaseRepository(
        session_factory=sessionmaker(bind=engine),
        entity_type=Weight,
        persistence_type=PGTestWeight,
        archive_persistence_type=PGTestWeightArchive,
    )

    with pytest.raises(EntityNotFoundException):
        repo.archive("does-not-exist", actor=ACTOR)


def test_unarchive_present_removes_archive_row(repo):
    w = _weight()
    repo.create(w, actor=SEED_ACTOR)
    repo.archive(w.id, actor=SEED_ACTOR)

    repo.unarchive(w.id)

    with repo.session_factory() as session:
        assert session.get(PGTestWeightArchive, w.id) is None
    # Original row is untouched by unarchive.
    assert repo.get_by_id(w.id) is not None


def test_unarchive_absent_is_noop(repo):
    repo.unarchive("does-not-exist")


# ---------------------------------------------------------------------------
# Actor attribution — this backend stamps rather than merely accepting
# ---------------------------------------------------------------------------


def _stored_actor(repo, persistence_type, entity_id: str) -> str:
    with repo.session_factory() as session:
        row = session.get(persistence_type, entity_id)
        assert row is not None
        return row.data["updated_by"]


def test_create_records_the_actor_argument_in_the_payload(repo):
    """The argument wins over whatever the entity carried.

    `BaseOwnerEntity.__post_init__` falls back to the owner when nothing set
    `updated_by`, which is a plausible-looking value that is wrong whenever
    someone other than the owner writes — a coach, or a job. Asserting
    against that fallback is what proves the argument is the source.
    """
    w = _weight()
    assert w.updated_by == "p1"

    repo.create(w, actor=ACTOR)

    assert _stored_actor(repo, PGTestWeight, w.id) == ACTOR


def test_save_records_the_writer_not_the_previous_one(repo):
    """A second writer's edit is attributed to the second writer."""
    w = _weight()
    repo.create(w, actor=SEED_ACTOR)

    w.weight = 190.0
    repo.save(w, actor=ACTOR)

    assert _stored_actor(repo, PGTestWeight, w.id) == ACTOR


def test_archive_stamps_the_copy_and_leaves_the_original_attribution(repo):
    """Archiving attributes the copy without rewriting who edited the original.

    The archive copy is a new record and gets the archiver's name. The live
    row must keep its own history — under a 6-year retention policy, an
    archive operation silently overwriting the original's audit field would
    lose the only record of who last edited it.
    """
    w = _weight()
    repo.create(w, actor=SEED_ACTOR)

    repo.archive(w.id, actor=ACTOR)

    assert _stored_actor(repo, PGTestWeightArchive, w.id) == ACTOR
    assert _stored_actor(repo, PGTestWeight, w.id) == SEED_ACTOR
