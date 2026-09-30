# Tasks: Google Health authorization and notifications

Rules:

- Tasks are ordered; each left the affected package(s) green (`cd backend/core && uv run pytest`, `cd backend/api && uv run pytest --deselect tests/test_session_store.py::test_unique_token_hash_is_enforced`, and `cd backend && uv run pyright` adding no error to the branch-point set of 3, all in `core/tests/test_smoke.py`).
- Each task was test-first: a commit with failing tests, then the commit that makes them pass.

## Checklist

- [x] 1. Mirror the `fitbits` provider contract in core: provider constants, D-13 fields, the three filters as deep copies, `select_active`, and a participant lookup that resolves a migrated participant to the Google record. _(Story 2)_
  - `domain/models/fitbit.py`, `adapters/mongo/model/mongo_fitbit.py`, `adapters/mongo/repositories/mongo_fitbit_repository.py`; tests `backend/core/tests/test_mongo_fitbit_provider.py` (`a96d56c`, `fe61693`).
- [x] 2. Pin the selection table, filter equality and copies, visibility and write shape; repeat visibility against a real `mongo:4.0.6`. _(Story 2)_
  - tests `backend/core/tests/test_mongo_fitbit_provider.py`, `backend/core/tests/test_mongo_fitbit_provider_real_mongo.py` (`d2cc115`).
- [x] 3. Carry a staff link through Google consent to one `pending` Google record: `links`, `authorize` with the `gh_oauth` cookie, finishAuth's insert, supersede and `completeMigration` publish; add the producer's `queue` parameter. _(Stories 1, 2)_
  - `google_health/{__init__,settings,tokens,oauth,google_client,store}.py`, `event_handlers/{ports,celery_producer}.py`, `main.py`; tests `test_google_health_oauth.py`, `test_celery_producer.py`, harness `tests/google_health_harness.py` (`4734e4b`, `6d237ca`).
- [x] 4. Refuse forged, replayed, expired, cross-audience, cross-browser, partial and misconfigured authorizations without a write; revoke a rejected grant only when no active record shares it; strip `/api/googleHealth` query strings from access logs. _(Stories 1, 2, 4)_
  - `oauth.py`, `settings.py`, `tokens.py`, `main.py`; tests `test_google_health_oauth.py`, `test_google_health_settings.py` (`eb3dee4`, `675c986`).
- [x] 5. Serialize and recover the migration: link claim before the exchange, participant and account locks, ownership recheck, carried `migratedAt`, migration hold, and a fault injected after every step. _(Story 2)_
  - `oauth.py`, `tokens.py`, `store.py`; tests `test_google_health_migration_concurrency.py` (`1d014dd`, `73f84f4`).
- [x] 6. Receive notifications behind a `SignatureVerifier` port: bounded read, secret handshake, object or array bodies, three interval forms, per-group publish on `scheduler_new`, 204/400/401/413/503; add the route to `EXPECTED_EXEMPTIONS`. _(Story 3)_
  - `google_health/notifications.py`; fixtures `tests/fixtures/google_health_notifications/`; tests `test_google_health_notifications.py`, `test_write_routes_require_auth.py` (`1e09549`, `72e826b`).
- [x] 7. Add `tink>=1.16,<2` (locked 1.16.1, transitives `absl-py`, `protobuf`, `bazel-runfiles`) to `openwellness-api`, after checking it on PyPI. _(Story 3)_
  - `backend/api/pyproject.toml`, `backend/uv.lock` (`e480e4c`).
- [x] 8. Verify signatures with Tink behind a key-id-aware keyset cache (60 s refetch floor, 5 s fetch, 401 versus 503); validate `GOOGLE_HEALTH_KEYSET_URL` as https; add the six-check selfcheck with bundled data. _(Stories 3, 4)_
  - `google_health/{signature,selfcheck,settings,__init__}.py`, `google_health/data/`; fixtures `tests/fixtures/google_health_signature/` (openssl vectors and `gen_vectors.sh`); tests `test_google_health_signature.py` (`31f1769`, `e480e4c`).
- [x] 9. Write this specification. _(all stories)_
- [ ] 10. Merge, then have the consuming project point its `openwellness` submodule at the merge commit, rebuild `ow_api` without cache, and confirm in-network: an anonymous `POST /api/googleHealth/links` gives 401, `GET /api/googleHealth/authorize?t=x` gives 503 while the Google keys are unset, `fitbitHeartRecord` with `{}` still gives 400 `Missing studyId`, and the selfcheck prints six PASS lines inside the image.
