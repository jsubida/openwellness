# Tasks: Event-handler webhooks and sync-user provisioning

Rules:

- Tasks are ordered; each left the affected package(s) green (`cd backend/core && uv run pytest`, `cd backend/api && uv run pytest`, `cd backend && uv run pyright` at or below the branch-point count of 3 errors).
- Each task was test-first: a commit with failing tests, then the commit that makes them pass.

## Checklist

- [x] 1. Answer `POST /api/eventHandlers/fitbitHeartRecord` with frame's pre chain and exact bytes, publishing through a `TaskPublisher` port. _(Story 1)_
  - `event_handlers/hapi.py`, `ports.py`, `sync_gateway.py`; tests `backend/api/tests/test_event_handlers_sync_gateway.py` (`7adceda`, `ad23720`).
- [x] 2. Add `celery>=5.4` (locked 5.6.3, unchanged) and `bcrypt>=4.2` (locked 5.0.0) to `openwellness-api`, after checking both on PyPI. _(Stories 1, 3)_
  - `backend/api/pyproject.toml`, `backend/uv.lock` (`c43b4e9`).
- [x] 3. Publish protocol-2 JSON to queue `celery` via `send_task` on the shared `CELERY_BROKER_URL`. _(Story 1)_
  - `event_handlers/celery_producer.py`; tests `backend/api/tests/test_celery_producer.py` (`442871f`, `e3af7c5`).
- [x] 4. Interpret payloads exactly as hapi does, from 44 live frame captures. _(Stories 1, 2)_
  - `parse_hapi_payload`, `read_hapi_payload` in `hapi.py`; fixture `tests/fixtures/frame_payload_matrix.json`; tests `test_event_handlers_payload.py` (`295823f`, `b58bac9`).
- [x] 5. Read study component settings through frame's `studyComponentSetting` view and studies from Mongo. _(Story 1)_
  - `event_handlers/couchbase_views.py`, `mongo_readers.py`; tests `test_event_handlers_readers.py` (`4bd587a`, `8227f6d`).
- [x] 6. Mount the event-handler router in `create_app()` with production deps and a last-registered hapi-404 catch-all; extend `EXPECTED_EXEMPTIONS`. _(Stories 1, 2)_
  - `event_handlers/__init__.py`, `main.py`, `tests/conftest.py`; tests `test_event_handlers_catchall.py`, `test_write_routes_require_auth.py` (`8d2a322`, `f6af0a6`).
- [x] 7. Serve `activity` and `post`; skip legacy `STUDY_SPECIFIC` studies on `activity` without reads. _(Story 1)_
  - `event_handlers/legacy_studies.py`, `sync_gateway.py`; tests `test_event_handlers_sync_gateway.py` (`971422d`, `25f3c3e`).
- [x] 8. Read SMART Conditions through `condition/byOwnerAndWeekAndCreatedAt` and participants by `couchId`. _(Story 1)_
  - `couchbase_views.py`, `mongo_readers.py`; tests `test_event_handlers_readers.py` (`3aad2ab`, `9711507`).
- [x] 9. Serve `weight` with frame's inline pre and the SMART `waitForWeight` path (option 7A). _(Story 1)_
  - `sync_gateway.py`; tests `test_event_handlers_sync_gateway.py` (`6c3ed5f`, `5d559f8`).
- [x] 10. Reproduce the ActiGraph `ValidationCode` echo and V8 `EventNotification` dates from live captures. _(Story 2)_
  - `event_handlers/actigraph_notification.py`; fixture `tests/fixtures/frame_actigraph_matrix.json`; tests `test_event_handlers_actigraph_notification.py` (`42be290`, `04df5c9`).
- [x] 11. Read devices by serial number (strings only) and participants by id. _(Story 2)_
  - `mongo_readers.py`, `ports.py`; tests `test_event_handlers_readers.py` (`fff8682`, `9a0144c`).
- [x] 12. Serve `POST /api/eventHandlers/actigraph` with frame's handshake and pre chain; bare 200 without a query for an absent or non-scalar `subjectId`. _(Story 2)_
  - `event_handlers/actigraph.py`; tests `test_event_handlers_actigraph.py` (`964bde4`, `7a2a825`).
- [x] 13. Provision, read and delete sync users through the SG admin interface; add `SYNC_GATEWAY_ADMIN_URL` and `SYNC_GATEWAY_DB` settings. _(Story 3)_
  - `backend/core/.../drivers/sg_admin_user_repository.py`, `sync_user_repository.py`, `settings.py`; tests `backend/core/tests/infrastructure/test_sg_admin_user_repository.py`, `backend/core/tests/integration/test_sg_sync_user_repository.py` (`a2b0fc6`, `6604ede`).
- [x] 14. Build frame-shaped participant and user documents and a node-verifiable bcrypt hash; replay frame's Joi on 69 cases. _(Story 3)_
  - `frame_participants/documents.py`; fixture `tests/fixtures/frame_participant_joi_matrix.json`; tests `test_frame_participants_documents.py` (`a9b0eaa`, `1e3df2a`).
- [x] 15. Serve `POST /api/participants` with SG-first provisioning and reverse-order compensation, behind `require_write_principal`. _(Story 3)_
  - `frame_participants/__init__.py`, `create.py`, `main.py`, `tests/conftest.py`; tests `test_frame_participants_create.py` (`f55c99e`, `c9d5cc5`).
- [x] 16. Write this specification. _(all stories)_
- [ ] 17. Merge, then have the consuming project point its `openwellness` submodule at the merge commit, rebuild `ow_api`, and confirm the routes answer in-network: `fitbitHeartRecord` with `{}` gives 400 `Missing studyId`, an unknown sub-path gives hapi's 404, and an anonymous `POST /api/participants` gives 401.
