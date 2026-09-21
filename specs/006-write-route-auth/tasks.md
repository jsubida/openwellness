# Tasks: Write-route authentication

## Checklist

- [x] 1. Add `require_write_principal` in `backend/api/src/openwellness_api/deps/principal.py`, attach it in `v1.py`, mark the six auth routes in `auth/router.py`, and cover 401/403/read/bootstrap behavior in `backend/api/tests/test_write_auth_hook.py`.
- [x] 2. Add the deployed-composition route walker in `backend/api/tests/test_write_routes_require_auth.py`.
- [ ] 3. Add a real bearer-token fixture (landed in 09-02) and invert `backend/api/tests/test_write_attribution.py` (09-06).
- [ ] 4. Silence the liveness access log in `backend/api/src/openwellness_api/main.py` (09-06).
- [ ] 5. Retire `enforce_principal` in `backend/api/src/openwellness_api/config.py` and `deps/principal.py` (09-06).