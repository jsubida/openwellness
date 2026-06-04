# openwellness-api

FastAPI service that exposes the OpenWellness `core` domain as a versioned,
[AIP](https://google.aip.dev/)-style REST API. It is the network source of
truth for all non-Python clients (dashboard, mobile).

Depends on [`../core`](../core) for domain models and repositories; this
package owns only the HTTP layer — routing, wire schemas, and the
translation between core's internal representation and the public contract.

## Design

- **AIP-compliant surface.** Resources follow Google's API Improvement
  Proposals: `collection/{id}` resource names (AIP-122), the five standard
  methods plus `:undelete` / `:purge` custom methods, camelCase JSON fields
  (AIP-140), cursor pagination (AIP-158), and a standard error envelope
  (AIP-193).
- **Thin routers over core.** Each resource router calls a core repository
  and serializes the result. The boundary work — epoch floats → RFC-3339,
  `id` → `name`, snake_case → camelCase — lives in `common/handlers.py`, so
  the full HTTP contract for a resource is visible in its own file.
- **Dependency injection.** Repositories are resolved per request through a
  `dependency-injector` container (inherited from core's `BaseContainer`).
  The API only binds the concrete `AppConfig`; everything else is reused.
  This is also the test seam — fakes are injected by overriding providers.

## Layout

```
src/openwellness_api/
  main.py        App factory, lifespan (opens/closes core drivers), /healthz
  v1.py          Aggregates every resource router under /v1
  config.py      Settings: Couchbase, Sync Gateway, Mongo, API knobs
  container.py   DI composition root (binds the concrete AppConfig)
  resources/     One router per entity (user, weight, goal, …)
  schemas/       One Pydantic wire model set per entity (Resource/Create/Update/List)
  common/        Shared helpers: serialization, pagination, filter, time_range, resource_name
  deps/          FastAPI dependencies: container repo resolver, request principal
  errors/        Core-exception → HTTP handlers + the AIP-193 error model
tests/           pytest suite backed by in-memory fakes (no DB required)
```

`resources/weight.py` is the canonical owner-scoped reference; `resources/user.py`
is the canonical top-level reference. Sister files mirror these skeletons.

## Running locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/). Run from the
workspace root (`../`), which resolves `core` and `api` together:

```bash
# install the workspace (api + core + dev tools)
uv sync --package openwellness-api

# serve with autoreload
uv run uvicorn openwellness_api.main:app --reload
```

Then:

- API root: `http://127.0.0.1:8000/v1`
- Interactive docs (OpenAPI): `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/healthz`

The lifespan opens a real Couchbase connection on startup, so point the
config at a reachable instance (see below) before serving.

## Configuration

All settings are read from the environment (or a `.env` file). Defaults
target a local stack.

| Variable | Default | Purpose |
| --- | --- | --- |
| `COUCHBASE_URL` | `couchbase://localhost` | Couchbase connection string |
| `COUCHBASE_USERNAME` | `Administrator` | Couchbase user |
| `COUCHBASE_PASSWORD` | `password` | Couchbase password |
| `COUCHBASE_BUCKET_NAME` | `openwellness` | Couchbase bucket |
| `SYNC_GATEWAY_URL` | `http://localhost:4984/openwellness` | Sync Gateway endpoint |
| `MONGO_URL` | `mongodb://localhost:27017` | Mongo connection string |
| `MONGO_DB` | `openwellness` | Mongo database name |
| `API_TITLE` | `OpenWellness API` | OpenAPI title |
| `API_DEFAULT_PAGE_SIZE` | `50` | Default `page_size` when unset |
| `API_MAX_PAGE_SIZE` | `1000` | Upper bound for `page_size` |
| `API_TIME_RANGE_MAX_SPAN_DAYS` | `7` | Max window for required-time-range resources |
| `API_CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed by CORS (dashboard SPA) |

## API conventions

- **Resource names.** Responses carry a `name` field — the full path, e.g.
  `users/abc` or `users/abc/weights/xyz` — not a bare `id`.
- **Standard methods.** `POST` (create), `GET` (get/list), `PATCH` (update,
  set-only fields via `exclude_unset`), `DELETE` (soft-delete / archive).
  Custom methods `POST .../{id}:undelete` and `POST .../{id}:purge` restore
  and hard-delete respectively.
- **JSON casing.** Request and response bodies use camelCase on the wire;
  server code uses snake_case. Unknown fields are ignored, not rejected.
- **Pagination.** List endpoints accept `page_size` and an opaque
  `page_token`; responses return the items plus `nextPageToken` (null on the
  last page).
- **Filtering.** Where supported, `filter=field=value` clauses joined by
  `AND`. Other operators (`>`, `OR`, `:`, …) return a clear 400 — v1
  implements a documented subset of AIP-160.
- **Time ranges.** Owner-scoped list endpoints accept `startTime` / `endTime`.
  High-cardinality time-series resources require the window and cap its span
  at `API_TIME_RANGE_MAX_SPAN_DAYS`.
- **Caller identity.** v1 has no real auth. The optional `X-Principal-Id`
  header stamps `updatedBy` on writes (defaults to `anonymous`).
- **Errors.** All failures return the AIP-193 envelope:
  ```json
  { "error": { "code": 404, "status": "NOT_FOUND", "message": "...", "details": [] } }
  ```

## Testing

The suite injects in-memory fakes for the core repositories, so no Couchbase
or Mongo is needed:

```bash
uv run --package openwellness-api pytest
```

## Deployment

Built and shipped via the workspace [`../Dockerfile`](../Dockerfile) (target
`api`), which produces a lean runtime image serving
`uvicorn openwellness_api.main:app` on port 8000 with a `/healthz` check.
Configure the container through the environment variables above.
