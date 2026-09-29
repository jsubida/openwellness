# Requirements: Event-handler webhooks and sync-user provisioning

Status: approved
Created: 2026-09-28

## Summary

Sync Gateway and ActiGraph call externally registered webhook paths under `/api/eventHandlers/*`, and coaches create participants through `POST /api/participants`. Today only the legacy hapi service (frame) answers them, which blocks the consuming project (opserver) from moving that traffic to OpenWellness. This specification adds the same paths to `ow_api` with frame's exact wire behaviour, so an edge route table can switch a path group between the two services with no caller-side change and switch it back the same way. Traceability: opserver HOOK-01 (Sync Gateway webhooks), HOOK-02 (ActiGraph webhook) and HOOK-03 (sync-user provisioning).

## User stories

### Story 1: Sync Gateway webhooks at frame's paths

As an operator, I want `ow_api` to answer Sync Gateway's four `document_changed` webhooks at their registered paths, so that the edge can route them to OpenWellness without reconfiguring Sync Gateway.

**Acceptance criteria**

- WHEN Sync Gateway POSTs to `/api/eventHandlers/fitbitHeartRecord`, `/activity`, `/post` or `/weight` THE system SHALL answer with frame's status code, body bytes, content type and hapi headers for every case in the captured fixtures.
- WHEN a request passes frame's pre chain (study id present, study component setting found, observer task named) THE system SHALL publish frame's exact Celery task name and arguments onto the shared `celery` queue and answer 204.
- WHEN the handler runs THE system SHALL read (settings view, study, participant, Condition) and publish only; it SHALL NOT write to any datastore.
- WHEN a task publish fails THE system SHALL answer hapi 500 so Sync Gateway sees the failure.
- WHEN an `activity` document belongs to one of the legacy studies named in `STUDY_SPECIFIC` THE system SHALL answer 204 without enqueueing or reading participant data.
- WHEN a SMART-study `weight` arrives for an active, non-buddy participant whose latest Condition is PENDING THE system SHALL publish frame's `jobs.smartRerandomization.waitForWeight` task.
- WHEN any other URI or method under `/api/eventHandlers` is requested THE system SHALL answer hapi's 404, never a FastAPI 307 or 405.

### Story 2: ActiGraph webhook and handshake

As an operator, I want `ow_api` to answer the ActiGraph webhook at `/api/eventHandlers/actigraph`, so that ActiGraph's registration and notifications keep working after the edge routes them to OpenWellness.

**Acceptance criteria**

- WHEN ActiGraph sends a `ValidationCode` handshake THE system SHALL answer 200 `Validation Code Received` and echo the code in `x-actigraph-hook-secret` with frame's exact bytes, and SHALL answer 500 rather than echo a code containing CR, LF or other header-illegal characters.
- WHEN a completed notification names a known device serial THE system SHALL publish `actigraphObserver` with `[participant couchId, EventNotification]`, where `start` and `end` equal V8's `JSON.stringify(new Date(x))` in the container's `TZ`, and answer 204.
- WHEN a notification is incomplete, or its device or participant is unknown THE system SHALL answer frame's bare 200 without publishing.
- WHEN the notification's `subjectId` is absent, null, an object or an array THE system SHALL answer a bare 200 without querying devices.
- WHEN the handler logs THE system SHALL NOT log the validation code, serial number, couchId or upload id.

### Story 3: Participant creation with a sync user

As a coach administrator, I want `POST /api/participants` on `ow_api` to create a participant together with its Sync Gateway user, so that a participant created through OpenWellness can sync the mobile app immediately.

**Acceptance criteria**

- WHEN an authenticated caller with the `admin` scope in the `root` group posts frame's payload THE system SHALL provision the Sync Gateway user first (name and password = couchId, channels `[couchId, "study:<studyId>", "sharedData"]`), then write the `participants` and `users` documents in frame's shape, and answer frame's 200 body.
- WHEN the Sync Gateway call fails THE system SHALL write nothing to Mongo.
- WHEN a Mongo write fails after provisioning THE system SHALL delete the documents it inserted, newest first, then delete the Sync Gateway user, and answer `400 Participant creation failed.`
- WHEN the payload fails frame's Joi rules THE system SHALL answer frame's 400 before any Sync Gateway or Mongo call.
- WHEN the stored password hash is checked by frame's node `bcrypt.compare` THE system SHALL produce a hash that verifies.
- WHEN a caller is anonymous THE system SHALL answer 401.

## Out of scope

- Routing. Merging this change sends no traffic to `ow_api`; the consuming project's edge decides per path group when it does. `/api/participants` stays on frame until a later change ports the rest of that group.
- The CPAP webhook, which stays on frame. `ow_api` answers its path with the catch-all 404.
- Frame's other twelve `/api/participants` routes.
- Webhook signature verification, stronger sync-user credentials and role/ownership authorization. See "Deferred security findings" in `design.md`.

## Open questions

- Whether the participant-creation response should keep `user.password` (the bcrypt hash), as frame returns it. See Deferred security finding 5 in `design.md`. It must be answered before `/api/participants` is routed to `ow_api`.
