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
put them in `backend/.env` (one shared file for the workspace). The full
variable list, defaults, and an example file live in the
[backend README](../README.md#configuration); the scheduler additionally reads
the `CELERY_*` variables documented there.

## Setup

From `backend/` (the workspace root), sync the environment. Pass
`--extra dev` so the test and type-check tools (`pytest`, `pyright`,
declared under `[project.optional-dependencies]`) land in the shared
workspace venv — a plain `uv sync` omits them, and `uv run pytest` then
fails to resolve `openwellness_core`:

```bash
cd backend
uv sync --extra dev

# A broker is required to run a worker. The defaults assume a local Redis:
docker run -d --name redis -p 6379:6379 redis:7
```

`core` installs as an editable package, so `import openwellness_core` works
from the test suite and any consumer without a rebuild.

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
