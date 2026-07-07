"""End-to-end proof: PGEngineFactory + PGBaseRepository + Alembic migration
against a real Postgres instance (via `testcontainers`).

Skipped cleanly when Docker is unavailable — the rest of the suite (see
`backend/core/tests/test_smoke.py`) is fully fake-backed and never needs a
live external service; this is the one exception, gated behind Docker.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from openwellness_core.adapters.postgres.model.pg_base_entity import Base, PGBaseEntity
from openwellness_core.adapters.postgres.repositories.pg_base_repository import (
    PGBaseRepository,
)
from openwellness_core.domain.models.weight import Weight
from openwellness_core.infrastructure.drivers.pg_engine import PGEngineFactory

CORE_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = CORE_DIR / "alembic.ini"


class SmokeWeight(PGBaseEntity, Base):
    __tablename__ = "_pg_foundation_smoke"


class SmokeWeightArchive(PGBaseEntity, Base):
    __tablename__ = "_pg_foundation_smoke_archive"


@dataclass
class _FakePostgresConfig:
    url: str
    pool_size: int

    def get_url(self) -> str:
        return self.url


def _run_alembic(*args: str, url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=CORE_DIR,
        env={**os.environ, "POSTGRES_URL": url},
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def postgres_url():
    try:
        from docker.errors import DockerException
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers is not installed")

    try:
        container = PostgresContainer("postgres:16-alpine", driver="psycopg")
        container.start()
    except DockerException as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Docker unavailable: {exc}")

    try:
        yield container.get_connection_url()
    finally:
        container.stop()


def test_full_crud_archive_cycle_against_real_postgres(postgres_url):
    _run_alembic("upgrade", "head", url=postgres_url)
    try:
        driver = PGEngineFactory(
            postgres=_FakePostgresConfig(url=postgres_url, pool_size=5)
        )
        repo = PGBaseRepository(
            session_factory=driver.session_factory,
            entity_type=Weight,
            persistence_type=SmokeWeight,
            archive_persistence_type=SmokeWeightArchive,
        )

        w = Weight(owner="p1", study_id="s1", weight=180.5)
        created = repo.create(w)
        assert created.id == w.id
        fetched = repo.get_by_id(w.id)
        assert fetched is not None
        assert fetched.weight == 180.5

        w.weight = 190.0
        repo.save(w)
        updated = repo.get_by_id(w.id)
        assert updated is not None
        assert updated.weight == 190.0

        repo.archive(w.id)
        # Archiving copies the row; the original is untouched.
        assert repo.get_by_id(w.id) is not None

        repo.unarchive(w.id)
        repo.unarchive(w.id)  # no-op: already absent from the archive table

        repo.delete(w.id)
        assert repo.get_by_id(w.id) is None
    finally:
        _run_alembic("downgrade", "base", url=postgres_url)
