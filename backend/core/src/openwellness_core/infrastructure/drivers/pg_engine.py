"""PostgreSQL engine/session driver.

Unlike `CBEntityRepository`, this is not a singleton: a pooled SQLAlchemy
`Engine` is designed to be shared via its own connection pool, so there is
no Sync-Gateway/cluster-client-style reason to enforce a single instance.
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config.app_config import PostgresConfig


class PGEngineFactory:
    """Builds a SQLAlchemy engine and session factory from `PostgresConfig`."""

    def __init__(self, postgres: PostgresConfig) -> None:
        self.engine: Engine = create_engine(
            postgres.get_url(), pool_size=postgres.pool_size
        )
        self.session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine
        )
