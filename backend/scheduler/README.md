# scheduler

Celery workers (and beat, if scheduled tasks are needed).

Depends on `../core` for the domain models, repository ports, and concrete
Couchbase/Mongo adapters. Runs scheduled and background work in-process
against the shared database — there is no HTTP layer here.

## Layout (Clean Architecture)

Dependencies point inward only — outer rings know about inner rings, never
the reverse:

| Ring | Location | Responsibility |
| --- | --- | --- |
| Entities | `openwellness_core.domain` | Domain models (e.g. `Participant`). |
| Use cases | `application/use_cases/` | Interactors with the business rules. Depend only on repository **ports** from `openwellness_core.application`. No Celery/DB imports. |
| Interface adapters | `infrastructure/tasks.py` | Thin Celery tasks: translate message args ↔ use-case request/response. No business logic. |
| Frameworks & drivers | `infrastructure/celery_app.py`, `config.py`, `container.py` | Celery app, broker config, and the DI container that binds the abstract ports to concrete Couchbase/Mongo adapters. |

The sample interactor `CountStudyParticipantsUseCase` is wired with its
concrete `ParticipantRepository` by `SchedulerContainer`; the
`openwellness.count_study_participants` task just resolves and invokes it.

## Configuration

The scheduler reads all settings from the environment. For local development,
put them in `backend/.env` (one shared file for the workspace). The variables
the scheduler cares about:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Message broker the worker pulls tasks from. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Where task results are stored. |
| `CELERY_TASK_DEFAULT_QUEUE` | `openwellness` | Default queue name for tasks. |
| `CELERY_TIMEZONE` | `UTC` | Timezone used by beat schedules. |
| `COUCHBASE_URL` | `couchbase://localhost` | Couchbase cluster the repositories connect to. |
| `COUCHBASE_USERNAME` | `Administrator` | Couchbase auth user. |
| `COUCHBASE_PASSWORD` | `password` | Couchbase auth password. |
| `COUCHBASE_BUCKET_NAME` | `openwellness` | Couchbase bucket holding the domain data. |
| `SYNC_GATEWAY_URL` | `http://localhost:4984/openwellness` | Sync Gateway endpoint. |
| `MONGO_URL` | `mongodb://localhost:27017` | Mongo connection string. |
| `MONGO_DB` | `openwellness` | Mongo database name. |

Example `backend/.env`:

```sh
# Celery broker / result backend
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Couchbase
COUCHBASE_URL=couchbase://localhost
COUCHBASE_USERNAME=Administrator
COUCHBASE_PASSWORD=password
COUCHBASE_BUCKET_NAME=openwellness

# Sync Gateway
SYNC_GATEWAY_URL=http://localhost:4984/openwellness

# Mongo
MONGO_URL=mongodb://localhost:27017
MONGO_DB=openwellness
```

## Setup

Run from the `backend/` workspace root so the shared `uv.lock` is used.

```sh
# Install the workspace (core + scheduler) into the virtualenv.
uv sync

# A broker is required to run a worker. The defaults assume a local Redis:
docker run -d --name redis -p 6379:6379 redis:7
```

## Running

Start a worker:

```sh
uv run celery -A openwellness_scheduler worker -l info
```

Enqueue the sample task:

```python
from openwellness_scheduler.infrastructure.tasks import count_study_participants
count_study_participants.delay("<study-object-id>")
```

For a periodic run, uncomment the `beat_schedule` entry in
`infrastructure/celery_app.py` and run:

```sh
uv run celery -A openwellness_scheduler beat -l info
```

## Testing

The tests exercise the use case and task adapters in-process with an in-memory
fake repository — no broker, Couchbase, or Mongo is required. `conftest.py`
seeds stub connection settings, so you can run them with nothing else running:

```sh
# From backend/scheduler
uv run pytest

# Or target this package from the workspace root
uv run pytest scheduler
```
