# Tasks: Write-route authentication

## Checklist

- [x] 1. Add `require_write_principal` in `backend/api/src/openwellness_api/deps/principal.py`, attach it in `v1.py`, mark the six auth routes in `auth/router.py`, and cover 401/403/read/bootstrap behavior in `backend/api/tests/test_write_auth_hook.py`.
- [x] 2. Add the deployed-composition route walker in `backend/api/tests/test_write_routes_require_auth.py`.
- [x] 3. Add a real bearer-token fixture (landed in 09-02) and invert `backend/api/tests/test_write_attribution.py` (09-06): four pre-R-10 tests inverted, plus header-only (403) and bearer-plus-header (403) refusal cases.
- [x] 4. Silence the liveness access log in `backend/api/src/openwellness_api/main.py` (09-06): `LivenessAccessLogFilter` on `uvicorn.access`, installed in the lifespan; structural tests in `backend/api/tests/test_liveness_log_filter.py`.
- [x] 5. Retire `enforce_principal` in `backend/api/src/openwellness_api/config.py` and `deps/principal.py` (09-06): `require_principal` kept as unconditionally strict (disposition in design.md); flag-state tests in `test_principal.py` and `test_auth_api.py` rewritten to prove no permissive mode survives; `backend/api/README.md` no longer documents `API_AUTH_ENFORCE_PRINCIPAL`.
- [ ] 6. Push the branch, merge it, and bump opserver's `openwellness` submodule so the running `ow_api` carries R-10 and the liveness filter (09-08).
- [ ] 7. Confirm live: `docker compose logs --since 45s ow_api` shows no `GET /healthz` lines once the submodule is bumped (09-06 Task 2 live check, deferred until the stack runs this branch).