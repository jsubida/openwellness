# Design: <feature name>

## Overview

How the solution works, in a few sentences. Note any alternatives considered and
why they were rejected.

## Affected components

Map the change onto the clean-architecture layers across the backend packages
(`backend/core`, `backend/api`, `backend/scheduler`):

| Layer | Module(s) | Change |
|---|---|---|
| domain | `backend/core/.../domain/` | |
| application | `backend/core/.../application/` | |
| adapters | `backend/core/.../adapters/{couchbase,mongo,postgres}/` | |
| infrastructure | `backend/core/.../infrastructure/{config,containers,drivers}/`, `backend/{api,scheduler}/.../config.py`, `.../container.py` | |

## Data models

New or changed entities/documents (Mongo collections, Couchbase documents,
Postgres tables/columns, pydantic settings/models). Include field names and types.

## Error handling

What can fail, and what the system does when it does (retry, log, skip, raise,
fail-fast at startup for misconfiguration).

## Test strategy

Which behaviors get unit tests, under each package's own `tests/` directory
(`backend/core/tests`, `backend/api/tests`, `backend/scheduler/tests`), mirroring
the source layout. Note required fakes/mocks (Couchbase, Mongo, Postgres, Redis,
Celery, external APIs are always mocked/faked in unit tests unless the task
calls for an integration test against a real containerized service).
