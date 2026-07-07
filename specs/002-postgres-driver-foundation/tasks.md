# Tasks: PostgreSQL Driver Foundation

Rules:

- Tasks are ordered; each leaves the affected package(s) green
  (`cd backend/core && uv run pytest`, and `cd backend && uv run pyright` for
  the workspace type-check).
- Each task should be completable in one sitting and reference the requirement(s) it serves.
- Check boxes (`[x]`) as tasks complete; add discovered tasks at the point they must run, not at the end.

## Checklist

- [x] 1. Add `sqlalchemy>=2.0`, `psycopg[binary]>=3`, `alembic>=1.13` to
      `backend/core/pyproject.toml` dependencies, and `testcontainers[postgres]`
      to the `dev` optional-dependencies list. Run `uv sync --extra dev` in
      `backend/core`. _(Story 1, Story 4)_
- [x] 2. Create `adapters/postgres/model/pg_base_entity.py` with the
      `PGBaseEntity` SQLAlchemy declarative mixin (id, owner, created_at,
      updated_at, revision, data JSONB) per design. _(Story 2)_
- [x] 3. Create `infrastructure/drivers/pg_engine.py` with `PGEngineFactory`
      consuming the Phase 1 `PostgresConfig` protocol (import it, do not
      redefine it) to build a SQLAlchemy `Engine` + `sessionmaker`. Add
      `backend/core/tests/infrastructure/drivers/test_pg_engine.py` verifying
      pool size is read from a fake `PostgresConfig` and no eager connection
      is opened. _(Story 1)_
- [x] 4. Create `adapters/postgres/repositories/pg_base_repository.py` with
      `PGBaseRepository[Entity, Persistence]` implementing
      `create/execute_query/get_by_id/get_by_query/list_all/save/delete`
      against the shared table shape, using a SQLAlchemy `Session` from the
      Phase 2 engine driver. `get_by_query` accepts a
      `sqlalchemy.sql.ColumnElement[bool]` where-clause per design. _(Story 2)_
- [x] 5. Add `archive()`/`unarchive()` to `PGBaseRepository`: `archive` copies
      the row into a `{tablename}_archive` companion table; `unarchive`
      deletes from it if present, no-op otherwise. _(Story 2)_
- [x] 6. Add `backend/core/tests/adapters/postgres/test_pg_base_repository.py`
      using an in-memory SQLite engine as the fake backing store, covering:
      create/get_by_id/save(update)/save(insert)/delete/list_all/
      archive/unarchive-present/unarchive-absent-is-noop, and a
      `get_by_query` range-filter case (proving the where-clause approach
      handles a `created_at BETWEEN` style query, the Phase-3-critical case
      from `CBWeightRepository.get_for_owner_between`). _(Story 2)_
- [x] 7. Set up `backend/core/alembic.ini` + `backend/core/alembic/env.py`,
      sourcing the DB URL from `PostgresSettings().get_url()` (Phase 1) rather
      than a hardcoded connection string. _(Story 3)_
- [x] 8. Generate `backend/core/alembic/versions/0001_initial.py` creating the
      example `_pg_foundation_smoke` table and its `_pg_foundation_smoke_archive`
      companion, matching the shared shape. _(Story 3)_
- [x] 9. Add `backend/core/tests/integration/test_pg_migration_smoke.py`:
      spins up `testcontainers.postgres.PostgresContainer`, runs
      `alembic upgrade head`, performs a full
      create/get/save/delete/archive/unarchive cycle through
      `PGBaseRepository` against the smoke table, runs
      `alembic downgrade base`, tears down. Skip cleanly
      (`pytest.mark.skipif` / catch container-start `DockerException`) when
      Docker is unavailable. _(Story 3, Story 4)_
- [x] 10. Run `cd backend/core && uv run pytest` (confirm the integration
      test either passes or skips depending on local Docker availability) and
      `cd backend && uv run pyright`; fix any type errors from the new
      SQLAlchemy-typed code. _(all stories)_
