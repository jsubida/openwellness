# Design: Storage Config Port Segregation & Backend Switch

## Overview

Split the monolithic `AppConfigInterface` into narrow, per-driver protocols
(already partially true — `CouchbaseConfig`, `SyncGatewayConfig`, `MongoConfig`
exist as `Protocol`s in `app_config.py`) and stop drivers from depending on
the fat interface. Add a `PostgresConfig` protocol alongside the existing
three. `AppConfigInterface` keeps composing all four as a convenience
aggregate for the composition root (`RepositoryContainer`/`BaseContainer`),
but individual drivers (`CBEntityRepository`, `MDBCollectionRepository`) take
only the one protocol they use as a constructor argument — this is the ISP
fix.

Move the duplicated pydantic-settings classes (`CouchbaseSettings`,
`SyncGatewaySettings`, `MongoSettings`) from `backend/api/.../config.py` and
`backend/scheduler/.../config.py` into a new
`openwellness_core/infrastructure/config/settings.py`. Both services' local
`AppConfig` classes shrink to composing the shared settings plus (new)
`PostgresSettings`, and implementing `AppConfigInterface`.

Add a `StorageBackendSettings` (env prefix none, single field
`storage_backend: Literal["couchbase-mongo", "postgres"]`, default
`"couchbase-mongo"`) also defined once in core. Each service's `AppConfig.__init__`
validates that the settings required by the selected backend are present,
raising a plain `ValueError` (caught nowhere special — an uncaught exception
during app/worker startup is the desired fail-fast behavior, consistent with
how `pydantic_settings.BaseSettings` already raises `ValidationError` on bad
env values).

**Alternative considered:** making `postgres` fields on `AppConfigInterface`
required from the start (matching today's pattern for couchbase/mongo).
Rejected — it's the exact ISP violation this phase exists to fix; every
future third/fourth backend would keep compounding it.

**Alternative considered:** a `Literal` union type with a discriminated
sub-model (`CouchbaseMongoConfig | PostgresConfig`) instead of a flat
`storage_backend` field. Rejected for this phase as higher-ceremony than
needed — plain field + explicit `__post_init__` validation is enough for a
two-way switch, and it doesn't block Phase 4 from later introducing a
`Selector`-based DI switch on top of this same field.

## Affected components

| Layer | Module(s) | Change |
|---|---|---|
| domain | — | none |
| application | — | none |
| adapters | `backend/core/.../adapters/couchbase/*`, `.../adapters/mongo/*` | none (constructors unchanged; they already take `repo=`/`entity_type=`, not config) |
| infrastructure — config (core) | `backend/core/.../infrastructure/config/app_config.py` | Add `PostgresConfig` protocol; keep `AppConfigInterface` as the 4-property aggregate (`couchbase`, `sync_gateway`, `mongo`, `postgres`) plus new `storage_backend: str` property |
| infrastructure — config (core, new) | `backend/core/.../infrastructure/config/settings.py` (new file) | `CouchbaseSettings`, `SyncGatewaySettings`, `MongoSettings`, `PostgresSettings`, `StorageBackendSettings` — moved/added here, exported via `infrastructure/config/__init__.py` |
| infrastructure — drivers (core) | `backend/core/.../infrastructure/drivers/cb_entity_repository.py` | Constructor signature changes from `config: AppConfigInterface` to `couchbase: CouchbaseConfig, sync_gateway: SyncGatewayConfig` |
| infrastructure — drivers (core) | `backend/core/.../infrastructure/drivers/mdb_collection_repository.py` | Constructor signature changes from `config: AppConfigInterface` to `mongo: MongoConfig` |
| infrastructure — containers (core) | `backend/core/.../infrastructure/containers/repository_container.py` | `entity_repository`/`collection_repository` providers updated to pass `couchbase=app_config.couchbase, sync_gateway=app_config.sync_gateway` and `mongo=app_config.mongo` respectively, instead of `config=app_config` |
| config (api) | `backend/api/src/openwellness_api/config.py` | Remove local `CouchbaseSettings`/`SyncGatewaySettings`/`MongoSettings`; import from core; `AppConfig` composes core settings + validates backend requirements |
| config (scheduler) | `backend/scheduler/src/openwellness_scheduler/config.py` | Same change as api's `config.py` |
| ops | `.env.example` | Add `STORAGE_BACKEND`, `POSTGRES_URL`, `POSTGRES_POOL_SIZE` with explanatory comments |

## Data models

No entity/document changes. New pydantic-settings shapes only:

```python
# backend/core/src/openwellness_core/infrastructure/config/settings.py

class CouchbaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COUCHBASE_", extra="ignore")
    url: str = "couchbase://localhost"
    username: str = "Administrator"
    password: str = "password"
    bucket_name: str = "openwellness"

class SyncGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYNC_GATEWAY_", extra="ignore")
    url: str = "http://localhost:4984/openwellness"
    def get_url(self) -> str: return self.url

class MongoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONGO_", extra="ignore")
    url: str = "mongodb://localhost:27017"
    db: str = "openwellness"
    def get_url(self) -> str: return self.url

class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")
    url: str = ""
    pool_size: int = 5
    def get_url(self) -> str: return self.url

class StorageBackendSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    storage_backend: Literal["couchbase-mongo", "postgres"] = "couchbase-mongo"
```

`AppConfigInterface` (in `app_config.py`) gains:

```python
class PostgresConfig(Protocol):
    def get_url(self) -> str: ...
    @property
    def pool_size(self) -> int: ...

class AppConfigInterface(ABC):
    ...
    @property
    @abstractmethod
    def postgres(self) -> PostgresConfig: ...
    @property
    @abstractmethod
    def storage_backend(self) -> str: ...
```

Each service's concrete `AppConfig.__init__` performs the fail-fast check:

```python
def __init__(self) -> None:
    self._storage = StorageBackendSettings()
    self._couchbase = CouchbaseSettings()
    self._sync_gateway = SyncGatewaySettings()
    self._mongo = MongoSettings()
    self._postgres = PostgresSettings()
    if self._storage.storage_backend == "postgres" and not self._postgres.url:
        raise ValueError(
            "STORAGE_BACKEND=postgres requires POSTGRES_URL to be set"
        )
```

(Couchbase/Mongo settings keep non-empty defaults today, so there's nothing
to validate on the `couchbase-mongo` path beyond what pydantic already
enforces — this mirrors existing behavior exactly.)

## Error handling

- Invalid `STORAGE_BACKEND` value: `pydantic_settings` raises
  `pydantic.ValidationError` automatically because the field is typed
  `Literal["couchbase-mongo", "postgres"]` — no custom code needed, and the
  error message names the invalid value and the allowed set.
- `STORAGE_BACKEND=postgres` with empty `POSTGRES_URL`: explicit `ValueError`
  raised in `AppConfig.__init__`, surfaced as an uncaught startup exception
  (FastAPI lifespan / Celery worker boot both already crash loudly on
  constructor errors — no new exception handling required).
- No behavior change for the default `couchbase-mongo` path: existing
  Couchbase/Mongo defaults are unchanged, so a deployment that never sets
  `STORAGE_BACKEND` sees identical behavior to today.

## Test strategy

Unit tests added under `backend/core/tests/` (mirroring
`infrastructure/config/`) and one test each under `backend/api/tests/` and
`backend/scheduler/tests/` for their respective `AppConfig`:

- `test_settings.py` (core): each shared settings class picks up its env
  prefix correctly (e.g. `COUCHBASE_URL` → `CouchbaseSettings().url`); default
  values match today's; `StorageBackendSettings` defaults to
  `"couchbase-mongo"` and rejects an arbitrary string via
  `pydantic.ValidationError`.
- `test_app_config.py` (api and scheduler, one per service): constructing
  `AppConfig()` with `STORAGE_BACKEND=postgres` and no `POSTGRES_URL` raises
  `ValueError`; with `POSTGRES_URL` set it constructs cleanly; with
  `STORAGE_BACKEND` unset/`couchbase-mongo` it constructs cleanly using only
  Couchbase/Mongo defaults (no Postgres env needed) — use `monkeypatch.setenv`
  / `pytest`'s env fixtures, no real network/service required.
- `CBEntityRepository`/`MDBCollectionRepository` constructor tests: confirmed
  (via grep across `backend/{core,api,scheduler}/tests`) that no existing test
  constructs either class directly or references `AppConfigInterface` today,
  so the signature change is a clean addition with no call sites to migrate —
  add new unit tests for each covering construction with a narrow fake
  protocol (e.g. a `SimpleNamespace`/small dataclass satisfying just
  `CouchbaseConfig` + `SyncGatewayConfig`).
- No integration test against a real Postgres/Couchbase/Mongo instance is
  needed for this phase — nothing here talks to a live service yet.
