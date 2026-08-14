# Tasks: Write Correctness Gate

Rules:

- Tasks are ordered; each leaves the affected package(s) green
  (`cd backend/core && uv run pytest`, `cd backend/api && uv run pytest`,
  `cd backend/scheduler && uv run pytest`, and `cd backend && uv run pyright`
  for the workspace type-check).
- Each task should be completable in one sitting and reference the requirement(s) it serves.
- Check boxes (`[x]`) as tasks complete; add discovered tasks at the point they must run, not at the end.

**Signature-widening note.** Tasks 5 and 6 widen `EntityRepository` / `BaseCrudRepository` write
methods with a required `actor` parameter. Every implementer breaks until all are updated, so a
signature change and its implementer updates land in the *same* task — `cd backend && uv run pyright`
is the gate that proves none were missed.

## Checklist

- [ ] 1. Add the real-Sync-Gateway harness: Couchbase Server 6.6 CE + Sync Gateway 2.8.2 services in
      `docker-compose.yml` with a one-shot `couchbase-init` provisioner, bucket `spring`,
      `enable_shared_bucket_access: true`, and the verbatim production sync function. _(Story 3)_
  - Files: `docker-compose.yml`, `sync_gateway/sync_gateway.json.template`,
    `scripts/render_sync_gateway_config.sh`, `scripts/couchbase_init.sh`, `.env.example`.
  - Credentials templated from day one; the rendered `sync_gateway.json` is gitignored. Verify the
    sync function survives env substitution intact (it is JavaScript and may contain `$`).
  - Done when `docker compose up couchbase-init sync-gateway` reaches a healthy Sync Gateway whose
    `/{db}/` endpoint answers, with no literal password in a tracked file.
- [ ] 2. Make `channels` and `_rev` first-class on the domain `BaseEntity`, and update the class
      docstring, which currently asserts they belong only to the persistence layer. _(Story 1)_
  - Files: `backend/core/src/openwellness_core/domain/models/base_entity.py`.
  - Test first: `backend/core/tests/adapters/couchbase/test_channels_round_trip.py` — a document
    dict through `to_domain` → mutate an unrelated field → `from_domain` → dict, asserting both
    fields are byte-identical at the far end. Cover `update_entity_valid_fields` as a separate case;
    it applies the same `valid_fields()` filter on its own path.
  - `CBBaseEntity` is expected to need no edit. Prove that with the test rather than assuming it.
- [ ] 3. Add `ChannelsInvariantError` and `RevisionConflictError`, then the fail-closed guard on the
      shared Couchbase write path, implementing the design's decision table exactly. _(Story 2)_
  - Files: `backend/core/src/openwellness_core/adapters/exceptions.py`,
    `backend/core/src/openwellness_core/adapters/couchbase/repositories/cb_base_repository.py`.
  - Test first: `backend/core/tests/adapters/couchbase/test_channels_guard.py` — one case per table
    row, including the unverifiable-prior rejection and the `CBParticipantGroup` channel-derivation
    allowance; assert the exception's structured attributes and that no request reached the driver
    on the rejection paths.
  - Stamp the loaded-channels snapshot in `_from_doc` as a non-field shadow attribute; call the
    guard from `save` only. Log with the stable `%s`-interpolated prefix from the design.
- [ ] 4. Stamp the supplied actor in the driver instead of the `"scheduler"` literal, and raise
      `RevisionConflictError` on a Sync Gateway revision conflict with no adapter-side retry.
      _(Story 4)_
  - Files: `backend/core/src/openwellness_core/infrastructure/drivers/cb_entity_repository.py`.
  - Test first: the actor a caller supplies is the value that reaches the payload; the `"scheduler"`
    literal appears nowhere in the write path; a conflict response raises the typed error rather
    than the undifferentiated `GenericException`.
  - Leave `_sanitize` popping `_rev` from the body — the revision belongs in the `?rev=` query
    parameter. Confirm the parameter is now actually appended, which it was not before task 2.
- [ ] 5. Add `application/actors.py` and thread a required `actor` parameter through the repository
      ports and every implementer, in one commit. _(Story 4)_
  - Files: `backend/core/src/openwellness_core/application/actors.py` (new),
    `application/repositories/base_crud_repository.py`, `adapters/interfaces/entity_repository.py`,
    `adapters/couchbase/repositories/cb_base_repository.py`,
    `adapters/mongo/repositories/mongo_base_repository.py`,
    `adapters/postgres/repositories/pg_base_repository.py`.
  - Test first: `backend/core/tests/test_actors.py` — `system_actor("fitbit_sync")` yields
    `system:fitbit_sync`, `is_system_actor` round-trips, and the format is never id-shaped.
  - `cd backend && uv run pyright` must be clean before this task is checked off.
- [ ] 6. Pass the authenticated acting principal at every API write call site. _(Story 4)_
  - Files: `backend/api/src/openwellness_api/resources/*.py`, plus the container wiring that
    supplies the actor.
  - Test: `cd backend/api && uv run pytest` — a request writing a document persists the
    authenticated principal's id in `updatedBy`, and no call site falls back to a service name.
- [ ] 7. Add the real-Sync-Gateway round-trip integration suite with the second-subscriber
      visibility assertion, parameterized over the four sampled document types.
      _(Story 1, Story 3)_
  - Files: `backend/core/tests/integration/conftest.py`,
    `backend/core/tests/integration/test_sg_round_trip.py`.
  - Two-stage skip (dependency import, then Sync Gateway reachability probe), with the skip message
    naming the compose command — mirroring `test_pg_migration_smoke.py::postgres_url`.
  - The assertion is that a *second* Sync Gateway user subscribed to a document channel still sees
    the document after the round trip, not that our own entity still holds the array.
- [ ] 8. Add the guard-rejection re-fetch comparison and the stale-revision conflict case to the
      integration suite. _(Story 2, Story 3)_
  - Files: `backend/core/tests/integration/test_sg_guard_and_conflict.py`.
  - Rejection case: attempt the access-destroying write, catch `ChannelsInvariantError`, re-fetch
    the whole document through Sync Gateway and compare the entire body plus `_rev` against the
    pre-attempt snapshot.
  - Conflict case: read the same document twice, write the first copy, assert the second write
    raises `RevisionConflictError` and that the store reflects only the first write.
