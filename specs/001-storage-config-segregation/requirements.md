# Requirements: Storage Config Port Segregation & Backend Switch

Status: approved
Created: 2026-07-06

## Summary

`openwellness_core.infrastructure.config.app_config.AppConfigInterface` currently
forces every consumer to implement `couchbase`, `sync_gateway`, and `mongo`
properties, and the concrete `AppConfig`/settings classes that satisfy it are
copy-pasted verbatim between `backend/api/src/openwellness_api/config.py` and
`backend/scheduler/src/openwellness_scheduler/config.py`. This is Phase 1 of a
six-phase initiative to add PostgreSQL as an alternative persistence backend
(Couchbase+Mongo remains the other option). Before any Postgres code exists,
the config layer needs to (a) stop forcing every backend's settings on every
consumer (an Interface Segregation violation that gets worse with a third
backend), (b) stop duplicating identical settings classes across services, and
(c) introduce the `STORAGE_BACKEND` switch and a `PostgresConfig` shape that
later phases build on. When this ships, the two backend services (API,
scheduler) source their storage config from one place in `backend/core`, each
driver depends only on the protocol it needs, and a deployment can flip
`STORAGE_BACKEND` and get a clear startup failure if the corresponding
settings are missing — with no behavior change yet for the existing
Couchbase+Mongo path.

## User stories

### Story 1: Narrow config protocols per driver

As a backend engineer adding or maintaining a storage driver, I want each
driver to declare a dependency only on the config protocol it actually reads,
so that a driver for one backend is never coupled to another backend's
settings shape.

**Acceptance criteria**

- WHEN `CBEntityRepository` is constructed THE system SHALL require only a
  `CouchbaseConfig` and a `SyncGatewayConfig` (not the full `AppConfigInterface`).
- WHEN `MDBCollectionRepository` is constructed THE system SHALL require only
  a `MongoConfig` (not the full `AppConfigInterface`).
- WHEN a new `PostgresConfig` protocol is added to
  `openwellness_core.infrastructure.config.app_config` THE system SHALL define
  it with the minimum shape a Postgres driver needs (a connection URL and a
  pool size), with no driver consuming it yet.
- WHEN `AppConfigInterface` is inspected THE system SHALL expose `couchbase`,
  `sync_gateway`, `mongo`, and `postgres` as accessors on the composition
  object, but individual drivers SHALL NOT depend on `AppConfigInterface`
  itself — they depend on the single narrow protocol they use.

### Story 2: Single source of truth for shared settings

As a backend engineer, I want the Couchbase/Mongo/Sync-Gateway
pydantic-settings classes defined exactly once in `backend/core`, so that API
and scheduler can never drift out of sync on env var names, prefixes, or
defaults.

**Acceptance criteria**

- WHEN either service's `config.py` is read THE system SHALL show no
  redefinition of `CouchbaseSettings`, `SyncGatewaySettings`, or
  `MongoSettings` — both import the shared classes from
  `openwellness_core.infrastructure.config`.
- WHEN a service's `AppConfig` is constructed THE system SHALL compose the
  shared settings classes and implement `AppConfigInterface`, with no
  duplicated field definitions.
- WHEN a service-specific setting exists (API's CORS/auth/SMTP knobs,
  scheduler's Celery knobs) THE system SHALL keep it defined only in that
  service's own `config.py`, unmoved.

### Story 3: Explicit, fail-fast storage backend switch

As an operator deploying the API or scheduler, I want one `STORAGE_BACKEND`
environment variable that selects the persistence backend, and a startup
failure with a clear message if the selected backend's required settings are
absent, so misconfiguration is caught at boot instead of at the first failed
query in production.

**Acceptance criteria**

- WHEN `STORAGE_BACKEND` is unset THE system SHALL default to
  `couchbase-mongo` (the current behavior, unchanged).
- WHEN `STORAGE_BACKEND=couchbase-mongo` THE system SHALL require valid
  Couchbase, Sync Gateway, and Mongo settings and SHALL NOT require any
  Postgres settings.
- WHEN `STORAGE_BACKEND=postgres` THE system SHALL require a valid
  `POSTGRES_URL` and SHALL NOT require Couchbase, Sync Gateway, or Mongo
  settings to be present.
- WHEN `STORAGE_BACKEND` is set to any value other than `couchbase-mongo` or
  `postgres` THE system SHALL raise a configuration error at startup naming
  the invalid value and the two accepted values.
- WHEN `STORAGE_BACKEND=postgres` but `POSTGRES_URL` is empty or unset THE
  system SHALL raise a configuration error at startup rather than constructing
  successfully and failing later on first use.

### Story 4: `.env.example` reflects the new switch

As an operator setting up a new deployment, I want `.env.example` to document
`STORAGE_BACKEND` and the Postgres variables alongside the existing
Couchbase/Mongo ones, so I know both paths exist even though only
Couchbase+Mongo is wired to real drivers today.

**Acceptance criteria**

- WHEN `.env.example` is read THE system SHALL show `STORAGE_BACKEND`,
  `POSTGRES_URL`, and `POSTGRES_POOL_SIZE` documented with comments explaining
  they are only required when `STORAGE_BACKEND=postgres`, and that no
  Postgres driver exists yet as of this phase.

## Out of scope

- Any Postgres driver, adapter, or repository implementation (Phase 2).
- Any change to `RepositoryContainer` bindings or a DI `Selector` between
  backends (Phase 4) — this phase only makes the switch *readable* from
  config; nothing consumes it to change which repositories get built yet.
- Data migration tooling (Phase 6).
- Changes to `AuthSettings`, `RedisSettings`, `SmtpSettings`, `APISettings`, or
  `CelerySettings` — these are already service-specific and out of scope.
- Renaming existing env vars (`COUCHBASE_*`, `MONGO_*`, `SYNC_GATEWAY_*` keep
  their current names and prefixes).

## Open questions

(none — resolved during drafting: `STORAGE_BACKEND` accepts the literal
strings `couchbase-mongo` and `postgres`; `PostgresConfig` shape is
`get_url() -> str` plus a `pool_size: int` property, mirroring the existing
`MongoConfig.get_url()` convention.)
