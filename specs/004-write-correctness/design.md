# Design: Write Correctness Gate

## Overview

The loss is not one defect in one place. Reading the write path end to end turns up **three
distinct sites**, and a fix that addresses only the first leaves the other two live:

1. **Read-side field loss.** `CBBaseEntity.to_domain` (`adapters/couchbase/model/cb_base_entity.py:67-74`)
   dumps the persistence model, renames `rev` → `_rev`, then filters the dict through
   `entity_cls.valid_fields()`. The domain `BaseEntity` (`domain/models/base_entity.py`) declares
   exactly one field, `id`. So `channels` and `_rev` are admitted by the persistence model and then
   discarded one line later, never reaching the domain entity. On the next write they are
   reconstructed from the entity's defaults — `None` and `""`.
2. **The same filter, repeated on the mutation path.** `CBBaseRepository.update_entity_valid_fields`
   (`adapters/couchbase/repositories/cb_base_repository.py:74-85`) applies an incoming wire dict onto
   an existing entity using the identical `valid_fields()` filter, so a document round-tripped
   through that method loses the two fields even if it was read correctly.
3. **Actor overwrite in the driver.** `CBEntityRepository.update`
   (`infrastructure/drivers/cb_entity_repository.py:135`) unconditionally assigns
   `obj["updatedBy"] = "scheduler"` on every update, discarding whatever the caller supplied.

`CBBaseEntity` is **already correct** and needs no change: it declares `rev: str = Field(alias="_rev", default="")`
and `channels: list[str] | None = None` as first-class fields (`cb_base_entity.py:30-31`), and
`from_domain` already special-cases `rev` off the entity's `_rev` attribute (`cb_base_entity.py:48-49`).
The fix is therefore **one-sided**: once the domain `BaseEntity` declares the two fields,
`valid_fields()` admits them and both filter sites stop dropping them with no edit to either filter.
That is an assertion to prove with the round-trip test, not to assume.

`_sanitize` (`cb_entity_repository.py:165-168`) popping `_rev` out of the request *body* is correct
and stays: the Sync Gateway REST API takes the revision as a `?rev=` query parameter
(`cb_entity_repository.py:140-142`), not in the body. The bug is that `obj["_rev"]` is `""` because
the read path dropped it, so the query parameter is never appended and every update is a blind
write.

**Alternative considered and rejected: a lossless envelope.** The general fix is for the persistence
boundary to round-trip *every* stored field, carrying unrecognized keys in an opaque envelope rather
than filtering against a declared allowlist. That is the correct long-term shape and is filed as a
follow-up issue. It is rejected *for this spec* because the gate blocks a migration: a change
touching every entity's serialization is not the change to land under time pressure, and a narrow
two-field fix is reviewable in one sitting. The generalization is a follow-up, not a silent omission.

**Alternative considered and rejected: read-before-write inside the guard.** The guard needs the
document's prior `channels` to decide. Re-fetching the stored document on every write would answer
that question authoritatively, at the cost of doubling the request count on the hot write path and
introducing a TOCTOU window that does not currently exist. Instead the prior value rides on the
entity, stamped when the repository loaded it, and the unverifiable case fails closed (see the
decision table below).

## Affected components

| Layer | Module(s) | Change |
|---|---|---|
| domain | `backend/core/src/openwellness_core/domain/models/base_entity.py` | Declare `channels: list[str] \| None = None` and `_rev: str = ""` as dataclass fields; update the class docstring, which currently asserts the opposite (that `_rev`/`channels` live only in `adapters/`) |
| application | `backend/core/src/openwellness_core/application/repositories/base_crud_repository.py` | Widen `create`, `save`, `archive` with a required `actor: str` parameter |
| application (new) | `backend/core/src/openwellness_core/application/actors.py` | New: `SYSTEM_ACTOR_PREFIX`, `system_actor(job_name)`, `is_system_actor(value)` — the single place the machine-actor format is defined |
| adapters | `backend/core/src/openwellness_core/adapters/exceptions.py` | Add `ChannelsInvariantError` and `RevisionConflictError`, both subclassing `AdapterException`, both exported via `__all__` |
| adapters | `backend/core/src/openwellness_core/adapters/couchbase/repositories/cb_base_repository.py` | Stamp the loaded-channels snapshot in `_from_doc`; add `_loaded_channels_of` and `_assert_channels_invariant`; call the guard from `save`; thread `actor` through `create`/`save`/`archive` |
| adapters | `backend/core/src/openwellness_core/adapters/couchbase/model/cb_base_entity.py` | No change expected — verify by test that `to_domain` now retains both fields |
| adapters | `backend/core/src/openwellness_core/adapters/mongo/repositories/mongo_base_repository.py` | Signature parity only: accept and propagate `actor` |
| adapters | `backend/core/src/openwellness_core/adapters/postgres/repositories/pg_base_repository.py` | Signature parity only: accept and propagate `actor` |
| adapters | `backend/core/src/openwellness_core/adapters/interfaces/entity_repository.py` | Widen the driver port: `create(obj, actor)`, `update(doc_id, obj, actor)`, `save(obj, actor)` |
| infrastructure | `backend/core/src/openwellness_core/infrastructure/drivers/cb_entity_repository.py` | Stamp the supplied actor instead of the `"scheduler"` literal (`:135`); raise `RevisionConflictError` from `_process_response` on a Sync Gateway conflict (`:159-162`) |
| infrastructure | `backend/api/src/openwellness_api/resources/*.py` | Pass the authenticated principal at every write call site |
| tests | `backend/core/tests/`, `backend/core/tests/integration/` | Unit suites plus the real-Sync-Gateway integration suite (see Test strategy) |
| tests / harness | `docker-compose.yml`, `sync_gateway/sync_gateway.json.template`, `scripts/render_sync_gateway_config.sh`, `scripts/couchbase_init.sh` | Couchbase Server + Sync Gateway services and their templated config |

Because `EntityRepository` is an ABC with several implementers, a signature widening breaks every
implementer until all are updated — so a signature change and its implementer updates belong in the
**same** task, and `cd backend && uv run pyright` is the gate that proves it.

## Data models

Two new fields on the domain base entity:

```python
@dataclass
class BaseEntity:
    id: str = field(default_factory=lambda: str(uuid4()))
    channels: list[str] | None = None
    _rev: str = ""
```

`_rev` as a leading-underscore dataclass field generates an `__init__` parameter literally named
`_rev`, which is exactly the key `CBBaseEntity.to_domain` already constructs with after its
`rev` → `_rev` rename (`cb_base_entity.py:70-71`). No mapping shim is required.

**Why these are first-class on the domain entity rather than persistence-only.** Under Sync Gateway
the sync function is evaluated against the document alone — there is no side channel, no join, no
access to anything the writer did not put in the body. On-document access metadata is therefore not
a persistence detail; it is part of the entity's meaning. The deployed sync function, verbatim from
the production `sync_gateway.json`:

```javascript
function(doc, oldDoc) {
    function isRemoved() { return (isDelete() && oldDoc == null); }
    function isDelete()  { return (doc._deleted == true); }
    if (isRemoved()) { return; }
    var combined = [];
    combined.push(doc.owner);
    if (doc.channels != null) {
        combined = combined.concat(doc.channels);
    }
    channel(combined);
}
```

Read it closely: there is no `access()`, no `role()`, no `requireUser()`, and no validation of any
kind. Sync Gateway is not a validation boundary — it will accept a `channels: null` document without
complaint, evaluate `combined` to `[doc.owner]`, and push the resulting removal to every other
subscriber's replica. Nothing in the stack logs an error. That is why the guard must live on our
side of the wire.

**Forward compatibility.** A later migration to Postgres/PowerSync does not invalidate this shape:
the array either feeds PowerSync sync rules directly or normalizes into a membership table, and in
both cases having the value on the entity is the starting point. (Open item for that migration, not
this one: confirm PowerSync's `IN`-on-JSON-array support.)

**No schema change** is required in Couchbase — `channels` and `_rev` already exist on stored
documents. This spec stops discarding them in transit.

## Error handling

Two new adapter-layer exceptions, both subclassing `AdapterException` from
`adapters/exceptions.py`, both exported through `__all__`:

| Exception | Raised when | Structured attributes | Caller contract |
|---|---|---|---|
| `ChannelsInvariantError` | The guard refuses a write that would destroy document access | `doc_id`, `doc_type`, `prior_channels`, `outgoing_channels` | Not retryable. Indicates a caller bug; the caller must supply the correct channels |
| `RevisionConflictError` | Sync Gateway answers with a revision conflict for a stale `_rev` | `doc_id`, `attempted_rev` | The adapter performs **no** retry or merge; a caller wanting retry re-reads and re-applies itself |

`ChannelsInvariantError` is raised **before** any HTTP request is issued, so a rejected write cannot
have partially applied. Its raise site also emits a log record with a stable prefix, following the
module's existing lazy-interpolation style:

```python
logging.error(
    "Channels invariant violated for %s (type=%s); prior channels=%s",
    doc_id, doc_type, prior_channels,
)
```

The prefix is stable on purpose: a log-based alert rule on this signature is the intended operational
follow-up.

`RevisionConflictError` is raised from `_process_response`
(`cb_entity_repository.py:154-163`), which today collapses every Sync Gateway error into an
undifferentiated `GenericException`. That method receives only the parsed body, so the conflict is
detected either by matching `resp["error"] == "conflict"` or by threading `response.status_code`
through; the existing `get_by_id` path (`cb_entity_repository.py:91-92`) raising a typed `NotFound`
across the layer boundary is the precedent for doing this here.

### Guard decision table

The guard's semantics are fixed here so the implementation cannot drift. "Loaded channels snapshot"
is the value stamped onto the entity when the repository read it; "absent" means no snapshot exists
because the entity never passed through a repository read.

| prior revision | loaded channels snapshot | outgoing channels | outcome |
|---|---|---|---|
| absent (`_rev == ""`) | any | any | allowed — a create has no existing access to destroy |
| present | non-empty list | `None` or `[]` | **rejected** |
| present | non-empty list | different non-empty list | allowed — an intentional access change is not the failure mode |
| present | `None` or `[]` | `None` or `[]` | allowed — there was no access to lose |
| present | **absent** (entity never read through the repository) | `None` or `[]` | **rejected** — unverifiable prior, fail closed |

**The last row is an extension beyond the literal requirement, and it is deliberate.** The
requirement says "reject when the prior revision carried a non-empty array." When the prior state is
unverifiable, the literal reading permits the write — which makes "fail-closed" meaningless, since
the exact defect class this guard exists to catch (a caller constructing an entity by hand and
writing it back) produces precisely that state. Resolving it authoritatively would require the
read-before-write round trip rejected in the Overview. So it fails closed, and there is a test
asserting it does. The cost is that a legitimate caller must load the entity through the repository
before saving it, which is the intended usage anyway.

**One legitimate rewrite the guard must not fire on**: `CBParticipantGroup.from_domain`
(`adapters/couchbase/model/cb_participant_group.py:32`) derives `channels = [f"participantGroup:{entity.id}"]`
at mapping time. That is a non-empty array replacing a non-empty array — row 3, allowed. It gets an
explicit test so a future tightening of the guard cannot silently break participant groups.

**Guard placement.** `CBBaseRepository.save` (`cb_base_repository.py:87-89`) is the single update
path all ~30 `cb_*` repositories flow through, and it is where the guard is called. `create`
(`:37-39`) is deliberately not guarded — a create has no prior revision, which is row 1 of the table
anyway. `archive` (`:94-99`) re-reads through `get_by_id` before writing its copy, so its entity
carries a snapshot and passes through `save`'s guard normally.

**Prior-state mechanism.** `_from_doc` (`cb_base_repository.py:34-35`) stamps the loaded array onto
the entity as a non-field shadow attribute via `object.__setattr__(entity, _LOADED_CHANNELS_ATTR, ...)`,
mirroring how `CBBaseEntity` stashes `_archived` (`cb_base_entity.py:53`). It is a snapshot, not the
live `channels` field, precisely so a caller mutating `entity.channels` does not also mutate the
value being compared against.

## Test strategy

**Unit tests** under `backend/core/tests/`, mirroring the source layout, with Couchbase faked as in
the existing suites:

- `tests/adapters/couchbase/test_channels_round_trip.py` — a document dict → `to_domain` →
  mutate an unrelated field → `from_domain` → dict, asserting `channels` and `_rev` are byte-identical
  at the far end. Also covers `update_entity_valid_fields` as an independent path, since it applies
  the same filter separately.
- `tests/adapters/couchbase/test_channels_guard.py` — one test per row of the decision table above,
  including the unverifiable-prior rejection and the `CBParticipantGroup` derivation allowance;
  asserts `ChannelsInvariantError` carries its structured attributes and that no request reached the
  driver on the rejection paths.
- `tests/test_actors.py` — `system_actor("fitbit_sync") == "system:fitbit_sync"`, `is_system_actor`
  round-trip, and that the format is never id-shaped.
- Actor propagation tests at the repository level: the actor a caller passes is the value that
  reaches the driver payload, and the `"scheduler"` literal appears nowhere in the write path.

**Integration tests** under `backend/core/tests/integration/`, beside the existing Postgres smoke
test, running against the compose Couchbase Server + Sync Gateway services and **skipping cleanly**
when they are unreachable. The skip is a two-stage probe — dependency import first, then an HTTP
reachability check against the Sync Gateway URL — matching the existing
`test_pg_migration_smoke.py::postgres_url` structure, with the skip message naming the compose
command that starts the services.

- `integration/test_sg_round_trip.py` — for each covered document type: write, read back through the
  adapter, modify an unrelated field, write again, then assert via a **second Sync Gateway user**
  subscribed to one of the document's channels that the document is still visible to that user. The
  second-subscriber assertion is the point: it measures the actual production failure mode (silent
  removal from other subscribers' replicas) rather than the weaker proposition that our own object
  still holds the array. It also asserts `_rev` advanced and matches what Sync Gateway reports.
- `integration/test_sg_guard_and_conflict.py` — attempt an access-destroying write, catch
  `ChannelsInvariantError`, then **re-fetch the whole document through Sync Gateway and compare the
  entire body plus `_rev`** against the pre-attempt snapshot. Separately: read the same document
  twice, write the first copy, then assert the second write raises `RevisionConflictError` and that
  the store reflects only the first write.

**Document-type coverage** is a parameterized sample chosen for risk, one `@pytest.mark.parametrize`
tuple per type so adding a type is a one-line change:

| Type | Why it is in the sample |
|---|---|
| `ParticipantGroup` | Channels-heavy, and the only type that derives `channels` at mapping time |
| `FitbitRecord` | High volume — the type most written by scheduled jobs |
| `Post` | Channel-scoped reads (`get_for_channel_between`), so a channels loss is directly observable |
| `Weight` | Plain owner-scoped entity with no channel logic — the control case |

**Harness fidelity** is part of the test contract, not an implementation detail: Sync Gateway 2.8.2,
Couchbase Server 6.6 CE, `enable_shared_bucket_access: true`, a single bucket named `spring`, and the
verbatim production sync function reproduced above. A harness that diverges can pass on behavior
production does not have, which would make the gate worthless. Credentials are templated
(`sync_gateway.json.template` + env substitution, rendered output gitignored); no literal password is
committed.

## Actor format audit

The machine-actor format `system:{job_name}` was gated on a prior verification: if anything
downstream resolves `updatedBy` against a user record, a prefixed string would break it and machine
actors would need id-shaped well-known values instead. That audit was performed across all three
consuming repositories before the format was locked. Evidence:

| Repo | Evidence | Reading |
|---|---|---|
| `api` | `server/api/couchbase/docs.js:217,280` and `server/api/couchbase/goals.js:136,226` validate `updatedBy` as `Joi.string().required()` — a free-form string, no id format asserted, no lookup performed | not resolved |
| `api` | `server/models/couchbase/base.js:12` writes `this.updatedBy = owner \|\| ''`; `fitbit-record.js:38,66`, `fitbit-weight.js:21`, `study-settings.js:25` all assign it and never read it back | write-only |
| `coachapp` | 40 hits, all plain-string model fields or form controls (`_models/goal.ts:43`, `_models/user-settings.ts:24`, `add.component.ts:592`). A grep for `updatedBy` combined with `find\|filter\|lookup\|getUser\|byId\|populate\|resolve` returns **zero** hits | not resolved |
| `scheduler` | `schedulernew/common/infrastructure/cb_entity_repository.py:136` already writes a bare literal machine name; `adapters/mappers/resmed_data_mapper.py:16` does the same; `tests/sampleData/conversations.json:50` shows it persisted in fixture data | a non-id-shaped actor **already exists in production data** |
| this repo | `adapters/couchbase/model/cb_base_owner_entity.py:16` defaults the field to `"unknown"` | non-id-shaped default is the existing precedent |

**Conclusion: the format is safe.** No consumer joins `updatedBy` to a user record, and a
non-id-shaped value already flows through production documents today. `system:{job_name}` is locked
as written; no id-shaped well-known values are required.

## Out of scope

- **`updatedAtTzOffset` refresh on update.** The ancestor scheduler stamps a *server*-local offset in
  `update()` (`cb_entity_repository.py:135` in that codebase) which this repository's port dropped.
  Restoring that literal parity would be a regression, not a fix: `BaseOwnerEntity`
  (`domain/models/base_owner_entity.py:29`) already computes a *participant*-local offset at
  construction, which is the more correct value. Recorded here so the divergence is a decision rather
  than an oversight; carried onto the follow-up issue.
- **The lossless-envelope refactor**, **CPAP/ProcessedSleep coverage**, **CI enforcement of this
  suite**, and **any Couchbase/Sync Gateway version upgrade** — see `requirements.md` § Out of scope.
