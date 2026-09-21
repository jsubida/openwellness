# Design: Write-route authentication

## Overview

The `/v1` router installs one method-aware dependency, `require_write_principal`, so every included write route requires a verified bearer principal. The hook is attached in `build_v1_router()`, not `create_app()`, because the API test fixture composes its application from the builder and never calls the factory. A route-walking test checks the deployed composition and names any unguarded path.

A router-level dependency is preferred to 188 per-route dependencies because it centralizes the security contract. A post-registration walker was rejected because it would depend on FastAPI internals and re-derive method behavior after registration.

## Decisions corrected against the consuming project

- D-19's zero-exemption count was factually impossible: the six authentication POST endpoints are the bootstrap path. They are the only exemptions in this phase; Phase 10 adds the six event-handler routes in a reviewed diff.
- D-17's attachment site is `build_v1_router()`, not `create_app()`, to avoid a false-green test fixture.
- The 403 branch runs before the 401 branch because a client-supplied principal header is forbidden even when the request is also unauthenticated.
- The permissive `enforce_principal` rollout flag was retired in 09-06 after the authenticated write path was re-authored and tested. `AuthSettings` no longer declares it and nothing reads it, so no `API_AUTH_*` environment value can weaken authentication.

## `require_principal` disposition (09-06)

`require_principal` has zero production call sites: every write is covered by `require_write_principal`, and the only callers are its own unit and HTTP tests. It was kept, in the **unconditionally strict** form (verified bearer or 401), rather than removed:

- The write guard deliberately leaves reads open. `require_principal` is the one strict dependency a sensitive *read* route can opt into; removing it would mean re-deriving it the first time a read needs authentication.
- The third form, silently returning an unauthenticated principal with a "would-be 401" warning, is gone. It was the flag's failure mode and would survive the flag's removal if kept.
- It no longer takes `Request` or reads the auth container; with no setting to consult, a missing container cannot change its behaviour.

Relaxing enforcement per environment in future requires re-adding a mechanism in a reviewed diff; `test_auth_settings_has_no_permissive_flag` fails if a flag reappears.

## Affected components

| Layer | Module(s) | Change |
|---|---|---|
| domain | none | none |
| application | none | none |
| adapters | none | none |
| infrastructure | `backend/api/src/openwellness_api/deps/principal.py`, `v1.py`, `auth/router.py` | central write guard and six bootstrap exemptions |

## Data models

None.

## Error handling

Client-supplied principal headers on writes raise a 403 `PERMISSION_DENIED` envelope. Missing or invalid bearer authentication on non-exempt writes raises a 401 `UNAUTHENTICATED` envelope. Reads and marked authentication routes pass through.

## Test strategy

HTTP tests prove refusal and bootstrap behavior against in-memory repositories. A structural walker calls `create_app()`, verifies every write route carries the dependency or the six-route exemption marker, and independently requires at least 188 write routes.