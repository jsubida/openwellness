# Requirements: PostgreSQL Driver Foundation

Status: approved
Created: 2026-07-06

## Summary

Phase 2 of 6 in the Postgres-support initiative. `backend/core` currently has
two driver families implementing the `BaseCrudRepository` application
interface: `CBEntityRepository`/`CBBaseRepository` (Couchbase SDK + Sync
Gateway HTTP) and `MDBCollectionRepository`/`MongoBaseRepository` (pymongo).
This phase adds the third: a SQLAlchemy-based Postgres engine/session driver
and a `PGBaseRepository` implementing the same `BaseCrudRepository` interface,
plus Alembic migration plumbing — proven end-to-end against a real Postgres
instance, but with **no entity-specific repositories yet**. Phase 1
(`specs/001-storage-config-segregation`, approved) already added the
`PostgresConfig` protocol and `PostgresSettings`/`STORAGE_BACKEND` this phase
consumes; nothing here touches config again. When this ships, a developer can
point `PGEngineFactory` at a real Postgres, run one Alembic migration, and
exercise full CRUD + archive/unarchive through `PGBaseRepository` against a
throwaway JSONB-shaped table — proving the pattern Phase 3 will replicate
across all ~37 entity types.

## User stories

### Story 1: Postgres engine/session driver

As a backend engineer, I want a driver that builds a SQLAlchemy engine and
session factory from the existing `PostgresConfig` protocol, so entity
repositories in Phase 3 have a ready-made connection to depend on, matching
how `CBEntityRepository` and `MDBCollectionRepository` already work.

**Acceptance criteria**

- WHEN the driver is constructed with a `PostgresConfig`-satisfying object
  THE system SHALL build a SQLAlchemy `Engine` from `postgres.get_url()` and a
  session factory (`sessionmaker`) sized from `postgres.pool_size`.
- WHEN the driver is constructed THE system SHALL NOT open a network
  connection eagerly (SQLAlchemy engines are lazy by default) — matching
  `MDBCollectionRepository`'s eager-but-lazy-handshake `MongoClient()` call
  and `CBEntityRepository`'s explicit `initialize()` split.
- WHEN two instances of the driver are constructed with the same config THE
  system SHALL NOT be required to share a singleton connection (unlike
  `CBEntityRepository`, which enforces a single instance via `__new__` for
  Sync Gateway/cluster-client reasons that don't apply to a pooled SQLAlchemy
  engine).

### Story 2: Generic Postgres base repository

As a backend engineer porting an entity repository in Phase 3, I want a
`PGBaseRepository` that implements the full `BaseCrudRepository` interface
generically (parameterized by entity + persistence type, exactly like
`MongoBaseRepository`/`CBBaseRepository`), so each entity-specific subclass in
Phase 3 is a thin, near-mechanical port rather than new plumbing.

**Acceptance criteria**

- WHEN `PGBaseRepository.create/get_by_id/get_by_query/list_all/save/delete`
  are called THE system SHALL operate against a single JSONB-shaped table
  (`id TEXT PRIMARY KEY, owner TEXT NULL, created_at TIMESTAMPTZ, updated_at
  TIMESTAMPTZ, revision INTEGER, data JSONB`), with the persistence
  type owning the `Entity <-> row` mapping via `_to_row`/`_from_row`, mirroring
  `_to_doc`/`_from_doc` on the existing two base repositories.
- WHEN `save()` is called on an entity with no `id` THE system SHALL insert a
  new row; WHEN called on an entity with an existing `id` THE system SHALL
  update the existing row and increment `revision`.
- WHEN `archive(entity_id)` is called THE system SHALL copy the row into a
  companion `{table}_archive` table (same shape), leaving the original row
  untouched — mirroring Mongo's `{collection}_archive` pattern (chosen over
  Couchbase's same-bucket type-discriminator pattern, since Postgres tables
  are already per-entity like Mongo collections, not a single shared bucket).
- WHEN `unarchive(entity_id)` is called THE system SHALL delete the row from
  the `{table}_archive` companion table if present, and SHALL be a no-op (not
  an error) if absent — matching both existing implementations' documented
  no-op contract.
- WHEN `get_by_query` is called THE system SHALL accept a backend-appropriate
  query representation (a SQLAlchemy `Select` or a dict of equality filters —
  design decides which, consistent with how `execute_query`'s type already
  varies per backend: `str` N1QL for Couchbase, `dict` Mongo filter for
  Mongo).

### Story 3: Alembic migration plumbing

As a backend engineer, I want a working Alembic environment in `backend/core`
with one initial migration that creates the shared table shape, so Phase 3
can add one migration per entity using an established, tested pattern instead
of inventing migration tooling from scratch.

**Acceptance criteria**

- WHEN `alembic upgrade head` is run against a real Postgres instance THE
  system SHALL create the initial migration's table(s) successfully.
- WHEN `alembic downgrade base` is run afterward THE system SHALL drop them
  cleanly (round-trip proof the migration is reversible).
- WHEN the Alembic environment reads its target database URL THE system
  SHALL source it from `PostgresConfig`/`PostgresSettings` (Phase 1), not a
  hardcoded or separately-configured connection string.

### Story 4: Proven end-to-end against a real Postgres

As a backend engineer, I want at least one test that exercises the full
driver → repository → Alembic-migrated table path against a real Postgres
(not a fake), so Phase 3's entity ports rest on a foundation that's known to
work against the actual database engine, not just mocked interfaces.

**Acceptance criteria**

- WHEN the test suite runs in an environment with Docker available THE
  system SHALL spin up a real Postgres (via `testcontainers` or the
  repo's `docker-compose.yml` service), run the initial migration, perform a
  full create/get/save/delete/archive/unarchive cycle through
  `PGBaseRepository`, and tear down cleanly.
- WHEN Docker is unavailable THE system SHALL skip this test (not fail the
  suite) — consistent with the rest of the suite being fully fake-backed
  today (see `backend/core/tests/test_smoke.py`), where no test currently
  requires a live external service.

## Out of scope

- Any entity-specific Postgres repository/model (`PGWeightRepository`,
  `PGUserRepository`, etc.) — Phase 3.
- `RepositoryContainer`/DI `Selector` wiring that actually switches which
  repositories get built based on `STORAGE_BACKEND` — Phase 4.
- `docker-compose.yml` changes beyond what's needed to run the Phase 4
  integration test locally — full compose wiring (service definition,
  `depends_on`, healthcheck for the api/scheduler services) is Phase 5.
- Auth refresh-session store Postgres port (`auth_refresh_sessions` currently
  a raw pymongo collection outside the repository container) — Phase 3.
- Data migration/ETL tooling — Phase 6.
- Full normalization of any entity's schema — this phase and Phase 3 are
  JSONB-first by design; normalizing hot entities is an explicitly deferred
  future concern.

## Open questions

(none — resolved during drafting: archive uses a companion `{table}_archive`
table, not an `archived_at` column, to mirror Mongo's existing pattern most
closely; `get_by_query`'s representation is decided in design after weighing
a raw dict-filter approach against a typed `Select`.)
