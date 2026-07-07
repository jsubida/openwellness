# Tasks: Storage Config Port Segregation & Backend Switch

Rules:

- Tasks are ordered; each leaves the affected package(s) green
  (`cd backend/core && uv run pytest`, `cd backend/api && uv run pytest`,
  `cd backend/scheduler && uv run pytest`, and `cd backend && uv run pyright`
  for the workspace type-check).
- Each task should be completable in one sitting and reference the requirement(s) it serves.
- Check boxes (`[x]`) as tasks complete; add discovered tasks at the point they must run, not at the end.

## Checklist

- [x] 1. Create `backend/core/src/openwellness_core/infrastructure/config/settings.py`
      with `CouchbaseSettings`, `SyncGatewaySettings`, `MongoSettings` moved in
      verbatim from `backend/api/.../config.py` (byte-identical field
      defaults/prefixes), plus new `PostgresSettings` and
      `StorageBackendSettings`. Add unit tests in
      `backend/core/tests/infrastructure/config/test_settings.py` covering env
      prefix pickup and defaults for all five classes. _(Story 1, Story 3)_
- [x] 2. Add `PostgresConfig` protocol and `postgres`/`storage_backend`
      properties to `AppConfigInterface` in
      `backend/core/.../infrastructure/config/app_config.py`. _(Story 1, Story 3)_
- [x] 3. Export the new settings module from
      `backend/core/.../infrastructure/config/__init__.py` (check what's
      currently exported there and extend rather than replace). _(Story 2)_
- [x] 4. Update `CBEntityRepository.__init__` in
      `backend/core/.../infrastructure/drivers/cb_entity_repository.py` to take
      `couchbase: CouchbaseConfig, sync_gateway: SyncGatewayConfig` instead of
      `config: AppConfigInterface`; update its two internal reads
      (`config.couchbase.*` → `couchbase.*`, `config.sync_gateway.get_url()` →
      `sync_gateway.get_url()`). Add a unit test constructing it with a minimal
      fake satisfying just those two protocols. _(Story 1)_
- [x] 5. Update `MDBCollectionRepository.__init__` in
      `backend/core/.../infrastructure/drivers/mdb_collection_repository.py` to
      take `mongo: MongoConfig` instead of `config: AppConfigInterface`. Add a
      unit test constructing it with a minimal fake `MongoConfig`. _(Story 1)_
- [ ] 6. Update `RepositoryContainer` in
      `backend/core/.../infrastructure/containers/repository_container.py`:
      `entity_repository = DIFactory(CBEntityRepository, couchbase=app_config.couchbase, sync_gateway=app_config.sync_gateway)`
      and
      `collection_repository = DIFactory(MDBCollectionRepository, mongo=app_config.mongo)`.
      Run `cd backend/core && uv run pytest` to confirm nothing else references
      the old `config=` kwarg. _(Story 1)_
- [ ] 7. Rewrite `backend/api/src/openwellness_api/config.py`: delete the
      duplicated `CouchbaseSettings`/`SyncGatewaySettings`/`MongoSettings`;
      import the shared classes from `openwellness_core.infrastructure.config`;
      `AppConfig.__init__` composes them plus `PostgresSettings` and
      `StorageBackendSettings`, and raises `ValueError` when
      `storage_backend == "postgres"` and `postgres.url` is empty. Leave
      `APISettings`, `RedisSettings`, `SmtpSettings`, `AuthSettings` untouched.
      _(Story 2, Story 3)_
- [ ] 8. Add `backend/api/tests/test_app_config.py` covering: default
      (`couchbase-mongo`) constructs cleanly; `STORAGE_BACKEND=postgres` +
      unset `POSTGRES_URL` raises `ValueError`; `STORAGE_BACKEND=postgres` +
      set `POSTGRES_URL` constructs cleanly; `STORAGE_BACKEND=nonsense` raises
      `pydantic.ValidationError`. Use `monkeypatch.setenv`/`delenv` per case.
      _(Story 3)_
- [ ] 9. Repeat tasks 7-8 for
      `backend/scheduler/src/openwellness_scheduler/config.py` and
      `backend/scheduler/tests/test_app_config.py` — same shape, `CelerySettings`
      untouched. _(Story 2, Story 3)_
- [ ] 10. Update `.env.example` at the repo root: add a new section with
      `STORAGE_BACKEND`, `POSTGRES_URL`, `POSTGRES_POOL_SIZE`, with a comment
      noting Postgres has no driver yet as of this phase and both vars are
      only required when `STORAGE_BACKEND=postgres`. _(Story 4)_
- [ ] 11. Run `cd backend && uv run pyright` at the workspace root and fix any
      type errors surfaced by the constructor signature changes (containers,
      any remaining `AppConfigInterface`-typed call sites). _(Story 1)_
- [ ] 12. Full verification sweep: `cd backend/core && uv run pytest`,
      `cd backend/api && uv run pytest`, `cd backend/scheduler && uv run pytest`
      all green; grep the whole `backend/` tree for `config: AppConfigInterface`
      and `config=app_config` to confirm no stale call sites remain outside the
      two driver classes intentionally kept on the aggregate interface (none
      currently do, but the DI containers use `app_config` as a dependency name
      — confirm that's still the aggregate, not a narrowed one). _(all stories)_
