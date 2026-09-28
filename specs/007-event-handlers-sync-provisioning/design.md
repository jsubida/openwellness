# Design: Event-handler webhooks and sync-user provisioning

## Overview

`ow_api` serves five webhook routes and one participant route at frame's own paths, outside `/v1`:

- `POST /api/eventHandlers/fitbitHeartRecord`, `/activity`, `/post`, `/weight` (Sync Gateway `document_changed`)
- `POST /api/eventHandlers/actigraph` (ActiGraph handshake and notifications)
- `/api/eventHandlers{rest:path}`, all methods: hapi's 404 for every other URI under the prefix
- `POST /api/participants` (admin-only participant creation)

The webhook routes are **enqueue-and-return**: they run frame's read-only pre chain to choose a task, publish frame's exact Celery task name and arguments onto the shared `celery` queue that the existing `router` worker consumes, and answer. Workers do not change, so moving a path group back to frame is a pure edge route change.

Every response is byte-for-byte hapi parity. A caller cannot tell which service answered. Parity is defined by fixtures captured live from frame (api `6706a1e5`, hapi 21.4.10, node 22.23.1), not by reading frame's source, because the captures contradicted a reading of the source ten times in the payload rules alone (see Parity contract).

Alternatives rejected:

- **Port the observers into OpenWellness.** It moves worker code onto the critical path and breaks the "route change only" rollback.
- **Pydantic request models.** A validated body answers 422 in the OpenWellness envelope where frame answers 400 or 500.
- **Mount under `/v1` or `compat/`.** Sync Gateway and ActiGraph call fixed paths; the routes are permanent contracts, not compatibility shims.

## Affected components

| Layer | Module(s) | Change |
|---|---|---|
| domain | none | none |
| application | `backend/core/.../application/repositories/sync_user_repository.py` | `provision` and `delete` added to `SyncUserRepository` |
| adapters | none | none |
| infrastructure | `backend/core/.../infrastructure/drivers/sg_admin_user_repository.py` | new SG admin-interface client |
| infrastructure | `backend/core/.../infrastructure/config/settings.py` | `SyncGatewaySettings.admin_url`, `.db`, `.admin_db_url()` |
| infrastructure | `backend/api/.../event_handlers/` | new package: routes, hapi helpers, ports, readers, Celery producer |
| infrastructure | `backend/api/.../frame_participants/` | new package: `POST /api/participants` |
| infrastructure | `backend/api/.../main.py` | mounts both routers; lifespan builds their deps |

### Package layout

```
backend/api/src/openwellness_api/
  event_handlers/
    __init__.py              router assembly (SG, ActiGraph, catch-all last); build_event_handler_deps
    hapi.py                  hapi headers, Boom phrases, response helpers, parse_hapi_payload, read_hapi_payload
    ports.py                 reader and publisher Protocols, EventHandlerDeps (read + publish only)
    sync_gateway.py          fitbitHeartRecord, activity, post, weight; frame's pre chain
    actigraph.py             ActiGraph handshake and notification route
    actigraph_notification.py  ValidationCode echo, V8 Date serialization, EventNotification
    legacy_studies.py        STUDY_SPECIFIC parsing (lazy, cached, fail-closed)
    couchbase_views.py       settings and Condition readers over frame's views
    mongo_readers.py         study, participant and device readers
    celery_producer.py       ProducerSettings, CeleryTaskPublisher
  frame_participants/
    __init__.py              router behind require_write_principal; build_frame_participant_deps
    create.py                the handler, its checks and its compensation
    documents.py             Joi-equivalent validation, participant/user documents, bcrypt hash, response
```

## Parity contract

The fixtures under `backend/api/tests/fixtures/` are the source of truth. Each case replays frame's status, body bytes, content type and every header, including `content-length`:

| Fixture | Cases | Captured how |
|---|---|---|
| `frame_payload_matrix.json` | 44 request payloads | POST to frame's `fitbitHeartRecord` from inside the network |
| `frame_actigraph_matrix.json` | 36 HTTP responses, 108 V8 `Date` outputs | POST to frame's ActiGraph route; `node -e` in frame's container, `TZ=America/Chicago` |
| `frame_participant_joi_matrix.json` | 69 payload verdicts | frame's Joi 17.13.4 run on frame's own schema in frame's container |

Rules the captures established:

- **Payload order is hapi's.** Size (413 over 1 MiB, before reading the body), then content-type parsing (400s for malformed, duplicate-parameter or boundary-less headers), then per-mime parsing, then Bourne's `__proto__` rejection. Empty bodies depend on the mime type: JSON or no type gives `null` (500), `text/*` gives `""` (400).
- **Boom's phrase table, not Node's.** 413 is `Request Entity Too Large`.
- **Deep JSON parses.** V8's `JSON.parse` is iterative; `ow_api` falls back to an iterative parser past Python's recursion limit.
- **Success is 204 with no content type.** ActiGraph success is 204 `text/html`; only the handshake answers 200 with a body.
- **ValidationCode echo follows Node's `setHeader`.** Latin-1 characters go out as UTF-8 bytes; an array becomes one header line per element; CR, LF, DEL, BEL and anything above U+00FF answer 500.
- **Dates follow V8.** `start` and `end` reproduce all 108 captured `JSON.stringify(new Date(x))` outputs, including DST ambiguous and gap times, BCE and year-0 dates, and local times outside years 1..9999 (the zone's earliest offset before its first transition, its final rule after 9999).

## View-based reads

Handlers read what frame reads, where frame reads it. There is no N1QL:

- Study component settings: Couchbase view `studyComponentSetting`, frame's key range, `REQUEST_PLUS`, oldest row.
- SMART Conditions: view `condition/byOwnerAndWeekAndCreatedAt`, last row.
- Studies, participants (by `couchId` and by id) and devices (by `serialNumber`): frame's Mongo collections.

Views match frame's consistency and avoid an uncovered N1QL query falling back to a primary scan on the shared bucket. Device lookups accept strings only, so a payload cannot inject a Mongo operator.

## Celery producer

`CeleryTaskPublisher` sends protocol-2 JSON with `send_task` to queue `celery`, the queue `router` consumes. It reads the shared `CELERY_BROKER_URL` (env prefix `CELERY_`), the same key frame and `router` use, never an `OW_` copy. The Celery app is built lazily, once, under a lock, with no result backend and 2-second broker timeouts.

`ow_api` boots without `CELERY_BROKER_URL`; it logs one warning naming the key, and every publish then answers hapi 500. A failed publish always answers 500, never 204, so Sync Gateway sees the failure.

## SMART weight placement (D-04, option 7A)

Frame's SMART `weight` handler reads the participant and its latest Condition inline, then calls `jobs.smartRerandomization.waitForWeight`. `ow_api` keeps those reads inline and publishes the same task with the same arguments, `[participant _id hex, weight _id]`. `router` already routes that task.

Option 7B, a new scheduler task that does the reads, was rejected: it adds a scheduler release to the critical path and changes nothing a caller can observe.

## Sync-user provisioning

`POST /api/participants` provisions the Sync Gateway user **first**, with an idempotent `PUT /{db}/_user/{name}` on the admin interface, then writes Mongo in frame's order: `participants` insert, `users` insert, `$set userId`, `$set roles.participant`. If any Mongo step fails it deletes the inserted documents newest first, then the SG user. Frame creates both concurrently and its compensation deletes the wrong name; neither behaviour is reproduced.

- Authentication is the router-level `require_write_principal`; the handler then checks frame's `admin` scope and `root` group.
- Validation replays frame's Joi on 68 of 69 captured cases. The one allowed divergence is Joi's IANA TLD list: `ow_api` accepts `a@example.invalidtld`, which Joi rejects.
- Values Joi accepts but frame fails on after writing (an uncastable `assignedCoachId`, a whitespace-only `participantNumber`) are refused before any write.
- `hash_password` produces `$2b$10$` hashes, truncated to 72 UTF-8 bytes as node bcrypt does. Frame's node `bcrypt.compare` verifies them.
- An unset `SYNC_GATEWAY_ADMIN_URL` or `SYNC_GATEWAY_DB` fails this route only (500), never boot.

## Recorded deviations from frame

| ID | Where | Frame | `ow_api` | Why |
|---|---|---|---|---|
| absent `subjectId` | ActiGraph | `find({serialNumber: undefined})` drops the filter and matches an arbitrary device, enqueueing work for the wrong participant | bare 200, no query, for an absent, null, object or array `subjectId` | an object subject is also a Mongo operator injection |
| D-a | participants | hapi `simple` strategy 401 | OpenWellness 401 envelope | bearer JWT instead of Basic/session; reconciled when the group is routed |
| D-b | participants | `Boom.badRequest(error)` echoes the internal error | fixed `400 Participant creation failed.` | internal errors do not reach callers |
| D-c | participants | real `users.timeCreated` | real `users.timeCreated` | no divergence: measured in frame's container, Joi 17 calls the date factory per validation |
| D-03 | SG `activity` | legacy studies run dead inline code that reads the participant and Condition | 204 with no reads and no enqueue | the legacy branch never enqueues; its answers were 204 or 500 depending on data |
| publish failure | all webhooks | fire-and-forget; 204 even with the broker down | hapi 500 | a lost event shows up as a 500 in Sync Gateway's and the edge's logs instead of a silent 204 |
| unknown `TZ` | ActiGraph | V8 falls back silently | 500 | a shifted window corrupts a worker's data |
| `STUDY_SPECIFIC` unusable | `activity`, `weight` | parse at boot | lazy parse; 500 per request if absent or malformed | never guess that a study is non-legacy |

## Deferred security findings

These are known, accepted and not fixed here. Each reproduces frame's behaviour or depends on work outside this repository.

1. **ActiGraph signature verification (D-17).** The route has no credential and no signature check, as in frame. Anyone who can reach the edge can POST a forged "completed" notification and enqueue `actigraphObserver` for the participant who owns a known device serial. Forged handshakes only echo their own code.
2. **SG password equals couchId (D-14).** The sync user's name and password are both the couchId, which also appears in channel names. Fielded app builds depend on it; fixing it needs a mobile-app change. `ow_api` keeps the name out of every exception and log line for this reason.
3. **Sync Gateway webhook authentication.** The four SG routes are unauthenticated, as in frame. Sync Gateway sends no credential, so anyone who can reach the edge can trigger observer tasks for an owner id they know. Handlers only read and enqueue.
4. **WR-07 before any user-authenticated group is routed (D-16).** The `/v1` write guard (`require_write_principal`) authenticates the caller but does not authorize: any valid bearer can write any resource. `POST /api/participants` adds frame's `admin` scope and `root` group checks for itself, but role and ownership authorization must land before `/api/participants`, or any other user-authenticated group, is routed to `ow_api`.
5. **bcrypt hash in the create response (open question 5).** The 200 body includes `user.password`, the bcrypt hash, because frame returns it. The coach app does not read it. Whether to strip it is undecided and must be settled before `/api/participants` is routed to `ow_api`; `documents.participant_response` carries a comment pointing here.

## Data models

No new collections, documents or tables. `POST /api/participants` writes frame's existing `participants` and `users` shapes:

- `participants`: frame's Mongoose key set and order, ObjectId-typed references, `userId` appended by the link step.
- `users`: `email`, `isActive`, `password` (bcrypt), `username`, `location`, `roles` (`{participant: {pid, pnum}}` after linking), `timeCreated`, `verifiedId`.

New settings: `SyncGatewaySettings.admin_url` (`SYNC_GATEWAY_ADMIN_URL`) and `.db` (`SYNC_GATEWAY_DB`) in core; `ProducerSettings.broker_url` (`CELERY_BROKER_URL`) in api. The routes also read `STUDY_SPECIFIC` and `TZ`, the same keys frame reads.

## Error handling

- Webhook handlers read their dependencies inside their own `try`, so every failure is a hapi 500. The only log line is `eventHandlers/<route> failed: <ExceptionClass>`, with no body, owner, serial or setting value (six-year log retention).
- `SyncUserProvisioningError` carries the operation, status and SG reason only, never the user name or password. Transport errors are re-raised with their class name and the original suppressed, because the URL contains the name.
- Missing configuration never blocks boot: an unset broker URL, SG admin URL, `STUDY_SPECIFIC` or invalid `TZ` fails only the routes that need it.

## Test strategy

Unit tests under `backend/api/tests` use a local FastAPI app with a recording publisher and fake readers, and assert exact bytes. Fixture replays cover every captured frame answer; route-order and walking tests pin the unauthenticated surface (`EXPECTED_EXEMPTIONS` holds the six auth routes, the five webhook routes and the catch-all). `backend/core/tests/integration/test_sg_sync_user_repository.py` runs the SG admin client against a live Sync Gateway 2.8.2 and skips only when none is reachable. Mongo is `mongomock`; Couchbase views are faked at `bucket.view_query` with the real SDK option objects.
