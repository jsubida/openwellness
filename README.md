# OpenWellness

Open-source research platform.

## Layout

```
backend/
  core/         Shared Python package — domain models, db, settings
  api/          FastAPI service (network source of truth)
  scheduler/    Celery workers + beat

frontend/
  dashboard/    React web dashboard
  mobile/       Compose Multiplatform / KMP app
```

`core/` is imported directly by `api/` and `scheduler/`. All non-Python
clients (dashboard, mobile) talk to the API over HTTP.
