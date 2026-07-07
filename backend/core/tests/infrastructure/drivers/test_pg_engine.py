"""PGEngineFactory construction against the narrow PostgresConfig protocol."""

from dataclasses import dataclass

from openwellness_core.infrastructure.drivers.pg_engine import PGEngineFactory


@dataclass
class FakePostgresConfig:
    url: str
    pool_size: int

    def get_url(self) -> str:
        return self.url


def test_builds_engine_and_session_factory_from_narrow_postgres_protocol():
    # An unreachable host proves construction never opens a network
    # connection: SQLAlchemy engines connect lazily, so this must not raise.
    postgres = FakePostgresConfig(
        url="postgresql+psycopg://user:pass@nonexistent-host-xyz:5432/db",
        pool_size=7,
    )

    driver = PGEngineFactory(postgres=postgres)

    assert driver.engine.pool.size() == 7
    assert driver.session_factory.kw["bind"] is driver.engine


def test_two_instances_are_independent_not_singleton():
    postgres = FakePostgresConfig(
        url="postgresql+psycopg://user:pass@nonexistent-host-xyz:5432/db",
        pool_size=5,
    )

    first = PGEngineFactory(postgres=postgres)
    second = PGEngineFactory(postgres=postgres)

    assert first is not second
    assert first.engine is not second.engine
