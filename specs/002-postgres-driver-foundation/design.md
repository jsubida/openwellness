# Design: PostgreSQL Driver Foundation

## Overview

Add a third driver/base-repository pair alongside the existing Couchbase and
Mongo ones, following their exact structural pattern:

- **Driver** (`infrastructure/drivers/pg_engine.py`): `PGEngineFactory`, built
  from `PostgresConfig` (Phase 1), wraps a SQLAlchemy `Engine` +
  `sessionmaker`. Unlike `CBEntityRepository`, it is NOT a singleton — a
  pooled SQLAlchemy engine is designed to be shared via its own connection
  pool, and dependency-injector's `Singleton` provider (used in the container,
  not `__new__`) is sufficient, matching how `MDBCollectionRepository`
  actually behaves today (constructed once per `DIFactory`, but with no
  `__new__` enforcement — the `CBEntityRepository` singleton is there for a
  Sync-Gateway/cluster-client-specific reason: `cluster.wait_until_ready`
  side effects shouldn't repeat, which doesn't apply here).
- **Base repository** (`adapters/postgres/repositories/pg_base_repository.py`):
  `PGBaseRepository[Entity, Persistence]` implementing `BaseCrudRepository`,
  generic exactly like `MongoBaseRepository`/`CBBaseRepository`.
- **Persistence base** (`adapters/postgres/model/pg_base_entity.py`):
  `PGBaseEntity`, a SQLAlchemy declarative mixin (not a pydantic model like
  the Mongo/CB persistence bases) exposing the shared column shape, since
  SQLAlchemy ORM entities are the idiomatic Postgres persistence
  representation and Phase 3's entity subclasses will each declare their own
  `__tablename__` plus any promoted columns beyond the shared shape.
- **Migrations**: an Alembic environment rooted at
  `backend/core/alembic/`, `env.py` sourcing its URL from
  `PostgresSettings().get_url()` (Phase 1), with `alembic.ini`'s
  `sqlalchemy.url` left blank (env.py overrides it) so no connection string is
  duplicated between Alembic config and app config.

**Alternative considered:** giving `PGBaseRepository` a pydantic persistence
model like the other two backends (`_to_doc`/`_from_doc` style), with raw SQL
via `psycopg` directly instead of SQLAlchemy ORM. Rejected — SQLAlchemy Core
gives us parameterized queries, connection pooling, and Alembic integration
for free, and the ORM mixin still keeps entity-specific code in Phase 3 thin
(a `Column` declaration list, not hand-written SQL strings for every entity,
unlike Couchbase's N1QL-per-query-method pattern).

**Alternative considered:** `get_by_query` taking a plain `dict` filter
(mirroring `MongoBaseRepository.execute_query(query: dict)`). Rejected in
favor of a SQLAlchemy `ColumnElement[bool]` (a `where()`-clause expression)
because Phase 3 needs to port range queries like
`CBWeightRepository.get_for_owner_between` (`createdAt BETWEEN $start AND
$end`), which a flat equality-dict filter can't express without inventing a
query micro-language. A SQLAlchemy expression is the natural "native query"
representation for this backend, consistent with the existing pattern where
each backend's `execute_query`/`get_by_query` signature already differs to
match that backend's natural query type (N1QL string+params for Couchbase,
filter dict for Mongo).

## Affected components

| Layer | Module(s) | Change |
|---|---|---|
| domain | — | none |
| application | `application/repositories/base_crud_repository.py` | none — `PGBaseRepository` implements the existing interface unchanged |
| adapters (new) | `adapters/postgres/model/pg_base_entity.py` | New: SQLAlchemy declarative mixin, shared column shape |
| adapters (new) | `adapters/postgres/repositories/pg_base_repository.py` | New: `PGBaseRepository[Entity, Persistence]` implementing `BaseCrudRepository` |
| infrastructure — drivers (new) | `infrastructure/drivers/pg_engine.py` | New: `PGEngineFactory(postgres: PostgresConfig)` — engine + sessionmaker |
| infrastructure — migrations (new) | `backend/core/alembic/env.py`, `backend/core/alembic/versions/0001_initial.py`, `backend/core/alembic.ini` | New: Alembic environment + one migration for the shared table shape |
| dependencies | `backend/core/pyproject.toml` | Add `sqlalchemy>=2.0`, `psycopg[binary]>=3`, `alembic>=1.13` as plain dependencies (see below); add `testcontainers[postgresql]` to the `dev` extra |

**Dependency placement decision:** `backend/core/pyproject.toml` currently
lists `couchbase` and `pymongo` as unconditional top-level dependencies —
there is no existing precedent in this codebase for backend-conditional
optional extras (`[project.optional-dependencies]` today only has `dev`).
Adding `sqlalchemy`/`psycopg`/`alembic` as plain dependencies matches that
existing convention exactly and avoids introducing a new packaging pattern
one phase before Phase 4 decides how backend selection actually works at
runtime. The image-size cost of an unconditional Postgres driver in a
Couchbase+Mongo-only deployment is small (SQLAlchemy + psycopg are a few MB)
and consistent with today's tradeoff (a Mongo-only deployment already
carries the Couchbase SDK).

## Data models

Shared JSONB-first row shape (SQLAlchemy declarative mixin):

```python
# adapters/postgres/model/pg_base_entity.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_mixin

@declarative_mixin
class PGBaseEntity:
    id: str = Column(String, primary_key=True)
    owner: str | None = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    revision: int = Column(Integer, nullable=False, default=0)
    data = Column(JSONB, nullable=False)
```

Each Phase-3 entity subclass declares `__tablename__` and, where an existing
query needs it (e.g. `owner` + `created_at` range, matching
`CBWeightRepository.get_for_owner_between`), relies on the promoted `owner`/
`created_at` columns already on the mixin — no per-entity column needed for
the queries seen in the current codebase. A companion archive table is
generated per entity as `{tablename}_archive` with an identical column set
(no shared base class needed beyond reusing the same mixin with a different
`__tablename__`).

Initial migration (`0001_initial.py`) creates one example table
(`_pg_foundation_smoke`, matching the shape above, plus its
`_pg_foundation_smoke_archive` companion) purely to prove the migration
pattern end-to-end — this table is dropped/renamed in Phase 3 once real
entity migrations replace it; it is not a permanent table.

## Error handling

- `PGEngineFactory` construction: no eager connection (SQLAlchemy engines
  connect lazily), so a bad `POSTGRES_URL` surfaces on first actual query, not
  at construction — this differs from `CBEntityRepository.initialize()`
  (`wait_until_ready` blocks and raises immediately) and is a known,
  acceptable difference: Phase 4's composition root can call
  `engine.connect()` once at startup if eager-fail-fast is wanted, but that's
  a DI-wiring decision, not a driver concern.
- `PGBaseRepository.save()` on stale `revision` (optimistic-lock conflict): out
  of scope for this phase — no repository in this codebase currently checks
  Couchbase's `_rev` for conflicts either (see `CBEntityRepository.update`,
  which writes `?rev=` unconditionally); `revision` is tracked for future use
  but not yet enforced. Note this explicitly as an intentionally-dropped
  acceptance criterion candidate, matching the two existing backends'
  current (lack of) optimistic-concurrency enforcement.
- `unarchive()` on a non-existent archive row: no-op, not an error — matches
  both `MongoBaseRepository.unarchive` and `CBBaseRepository.unarchive`'s
  documented contract.
- Alembic migration failure (e.g. Postgres unreachable): propagates as
  whatever `alembic upgrade` raises natively (a `sqlalchemy.exc.OperationalError`)
  — no custom wrapping needed, this is a one-shot CLI operation, not
  request-path code.

## Test strategy

- `backend/core/tests/adapters/postgres/test_pg_base_repository.py`: unit
  tests using an in-memory SQLite engine (SQLAlchemy's `create_engine("sqlite://")`)
  as the fake backing store for `PGBaseRepository`'s CRUD/archive/unarchive
  behavior — SQLite supports enough of the shared shape (TEXT/JSON columns)
  to exercise the repository logic without a real Postgres, mirroring how the
  existing Mongo/Couchbase base-repository tests use in-memory fakes
  (`_FakeMongoCollection`/`FakeEntityRepository` in `test_smoke.py` and
  `test_repositories_queries.py`) rather than real external services.
- `backend/core/tests/infrastructure/drivers/test_pg_engine.py`: unit test
  that `PGEngineFactory` builds an `Engine` with the pool size read from a
  fake `PostgresConfig`, without opening a real connection.
- `backend/core/tests/integration/test_pg_migration_smoke.py` (new
  `integration` test directory, separate from the existing fully-faked unit
  suite): the one Story-4 test that runs Alembic against a real Postgres via
  `testcontainers.postgres.PostgresContainer`, decorated to skip cleanly (
  `pytest.mark.skipif`, checking Docker availability via
  `testcontainers`' own `DockerException` at container start, caught and
  turned into a skip) when Docker isn't available — this keeps
  `cd backend/core && uv run pytest` green in any environment (CI or local)
  while still proving the end-to-end path when Docker is present.
- No changes needed to any Mongo/Couchbase test — this phase adds a parallel,
  independent test surface.
