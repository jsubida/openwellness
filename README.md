# OpenWellness

Open-source platform for running wellness research studies. Participants
record wellness data from a mobile app, coaches and admins work from a web
dashboard, and a Python backend owns the domain and the datastores.

The repository is two workspaces — a [`backend/`](backend/README.md) uv
workspace of three Python packages, and a [`frontend/`](frontend/README.md)
pair of client apps. All non-Python clients talk to the API over HTTP; nothing
else crosses the backend boundary.

```text
  ┌────────────────┐      ┌─────────────────┐
  │   dashboard    │      │     mobile      │     frontend/ — HTTP clients
  │  (React SPA)   │      │  (Compose MP)   │
  └───────┬────────┘      └────────┬────────┘
          │       HTTP · /v1       │
          └───────────┬────────────┘
                      ▼
  ┌────────────────────┐    ┌──────────────────┐
  │        api         │    │    scheduler     │  backend/ — services
  │     (FastAPI)      │    │ (Celery workers) │
  └─────────┬──────────┘    └────────┬─────────┘
            │  import openwellness_core
            └────────────┬───────────┘
                         ▼
                 ┌───────────────┐
                 │     core      │                 backend/ — shared library
                 └───────┬───────┘
                         ▼
       Couchbase / Sync Gateway · MongoDB          (Redis brokers the scheduler)
```

## Packages

| Package | Role |
| --- | --- |
| [`backend/core/`](backend/core/README.md) | Shared Python library — domain models, repository ports, Couchbase/Mongo adapters, DI wiring. |
| [`backend/api/`](backend/api/README.md) | FastAPI service — the network source of truth, AIP-style REST under `/v1` plus email-OTP auth. |
| [`backend/scheduler/`](backend/scheduler/README.md) | Celery workers (and beat) for scheduled and background work. |
| [`frontend/dashboard/`](frontend/dashboard/README.md) | React web dashboard for coaches and admins. |
| [`frontend/mobile/`](frontend/mobile/README.md) | Compose Multiplatform (KMP) app for participants — Android + iOS. |

Every package follows the same **Clean Architecture** discipline — source
dependencies point only inward, outer rings reach inner ones through ports.
The shared vocabulary is defined once in the
[`core` glossary](backend/core/README.md#glossary); the frontend packages
mirror the same intent in their own idioms
([how](frontend/README.md#what-both-clients-keep-in-common)).

## Quick start

Each workspace README has the full prerequisites, configuration, and run
instructions; the short version:

```bash
# backend — API on http://localhost:8000 (see backend/README.md#configuration)
cd backend
uv sync --extra dev
uv run uvicorn openwellness_api.main:app --reload

# dashboard — http://localhost:5173
cd frontend/dashboard
npm install && npm run dev

# mobile — Android install (iOS: open frontend/mobile/iosApp in Xcode)
cd frontend/mobile
./gradlew :androidApp:installDebug
```

For a containerized backend, the root [`docker-compose.yml`](docker-compose.yml)
builds the multi-stage [`backend/Dockerfile`](backend/Dockerfile) and runs
`api`, `scheduler`, and a Redis broker off a shared `.env`.

## Testing

No suite needs a live datastore, broker, or backend — they all run against
in-memory fakes (MSW / Ktor `MockEngine` on the frontend):

```bash
cd backend/core       && uv run pytest
cd backend/api        && uv run pytest
cd backend/scheduler  && uv run pytest
cd backend            && uv run pyright            # type-check (workspace root)

cd frontend/dashboard && npm run test
cd frontend/mobile    && ./gradlew testAndroidHostTest
```
