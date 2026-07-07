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
from openwellness_core.domain.exceptions.domain_exception import (
    EntityNotFoundException,
)
from openwellness_core.domain.models.weight import Weight


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

    created = repo.create(w)

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

    saved = repo.save(w)

    assert saved.id
    assert repo.get_by_id(saved.id) is not None


def test_save_with_existing_id_updates_and_increments_revision(repo):
    w = _weight()
    repo.create(w)

    w.weight = 190.0
    repo.save(w)
    w.weight = 200.0
    repo.save(w)

    fetched = repo.get_by_id(w.id)
    assert fetched.weight == 200.0
    with repo.session_factory() as session:
        row = session.get(PGTestWeight, w.id)
        assert row.revision == 2


def test_delete(repo):
    w = _weight()
    repo.create(w)

    result = repo.delete(w.id)

    assert result == w.id
    assert repo.get_by_id(w.id) is None


def test_delete_missing_returns_none(repo):
    assert repo.delete("does-not-exist") is None


def test_list_all(repo):
    repo.create(_weight())
    repo.create(_weight())

    assert len(repo.list_all()) == 2


def test_get_by_query_range_filter(repo):
    old = _weight(owner="p1", created_at=1_000_000.0)
    recent = _weight(owner="p1", created_at=2_000_000.0)
    other_owner = _weight(owner="p2", created_at=1_500_000.0)
    repo.create(old)
    repo.create(recent)
    repo.create(other_owner)

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
    repo.create(w)

    repo.archive(w.id)

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
        repo.archive("does-not-exist")


def test_unarchive_present_removes_archive_row(repo):
    w = _weight()
    repo.create(w)
    repo.archive(w.id)

    repo.unarchive(w.id)

    with repo.session_factory() as session:
        assert session.get(PGTestWeightArchive, w.id) is None
    # Original row is untouched by unarchive.
    assert repo.get_by_id(w.id) is not None


def test_unarchive_absent_is_noop(repo):
    repo.unarchive("does-not-exist")
