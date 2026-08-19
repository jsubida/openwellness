# Requirements: Write Correctness Gate

Status: approved
Created: 2026-08-14

## Summary

The Couchbase adapter loses two fields on every read→modify→write cycle. `CBBaseEntity.to_domain`
filters the document through `entity_cls.valid_fields()`, and the domain `BaseEntity` declares only
`id` — so `channels` and `_rev` never reach the domain entity and come back as `None`/`""` on the
next write. Against the production Sync Gateway this is not a cosmetic loss: the deployed sync
function assigns `channel([doc.owner].concat(doc.channels || []))`, so a document written back with
`channels: null` collapses to the owner's channel alone and is **removed from every other
subscriber's replica**, with no HTTP error and no log line anywhere in the stack. A dropped `_rev`
additionally turns every update into a blind write with no conflict detection. A third defect sits
in the same write path: `CBEntityRepository.update` hardcodes `obj["updatedBy"] = "scheduler"`, so
no persisted document names the actor that actually wrote it. This spec makes `channels` and `_rev`
survive the round trip, adds a permanent fail-closed guard so an access-destroying write is refused
rather than silently applied, attributes writes to the real acting actor, and proves all of it
against a real Sync Gateway rather than a fake. It is a prerequisite gate: the consuming migration
(opserver milestone v1.2.0) ships no production write path until this lands.

Traceability: the four stories below correspond one-to-one to requirements DATA-01, DATA-02,
DATA-03 and DATA-04 in the consuming project's requirements register.

## User stories

### Story 1: Access and revision metadata survive the round trip (DATA-01)

As a participant, I want a document that another service reads and edits to keep reaching my phone,
so that an unrelated backend write never silently deletes content from my device.

**Acceptance criteria**

- WHEN a document is read through `CBBaseRepository.get_by_id` (or any read path that builds a
  domain entity via `CBBaseEntity.to_domain`) THE system SHALL populate `channels` and `_rev` on
  the returned domain entity with the values carried by the stored document.
- WHEN a wire dict is applied onto an existing entity through
  `CBBaseRepository.update_entity_valid_fields` THE system SHALL retain `channels` and `_rev`
  rather than discarding them through the `valid_fields()` filter.
- WHEN that entity is written back through `CBBaseRepository.save` THE system SHALL send the same
  `channels` array to Sync Gateway that was read, unless the caller changed it deliberately.
- WHEN the write succeeds THE system SHALL advance the entity's `_rev` to the revision Sync Gateway
  returned in its response.
- WHEN a write is attempted with a stale `_rev` and Sync Gateway answers 409 Conflict THE system
  SHALL raise a dedicated typed error and SHALL NOT retry or merge inside the adapter.

### Story 2: Access-destroying writes are refused, not applied (DATA-02)

As an operator, I want a write that would revoke a document's access to be refused before it leaves
the process, so that a defect in any of the ~30 `cb_*` repositories cannot silently unshare
participant data.

**Acceptance criteria**

- WHEN a write targets a document whose prior revision carried a non-empty `channels` array and the
  outgoing `channels` value is `None` THE system SHALL reject the write.
- WHEN the same write carries an empty list `[]` instead of `None` THE system SHALL reject it
  identically, because the production sync function collapses both to `[doc.owner]`.
- WHEN a write targets a document whose prior `channels` state cannot be verified (the entity was
  never loaded through the repository) and the outgoing `channels` value is empty or absent THE
  system SHALL reject the write, failing closed rather than assuming there was nothing to destroy.
- WHEN a rejection occurs THE system SHALL raise a dedicated exception before any HTTP request is
  issued to Sync Gateway, and the stored document SHALL be byte-identical (including `_rev`) to its
  state before the attempt.
- WHEN a rejection occurs THE system SHALL emit a log record naming the document id, the document
  type, and the prior channels array, with a stable message prefix suitable for alerting.
- WHEN a write changes `channels` from one non-empty array to a different non-empty array THE
  system SHALL allow it, because an intentional access change is not the failure mode being
  guarded.
- WHEN a document is created for the first time (no prior revision) THE system SHALL allow an empty
  or absent `channels` value, because there is no existing access to destroy.

### Story 3: The proof runs against a real Sync Gateway (DATA-03)

As a maintainer, I want the round-trip proof to run against a real Sync Gateway and Couchbase
Server rather than a fake, so that the guarantee is about the deployed system and not about our
own test doubles.

**Acceptance criteria**

- WHEN the integration suite runs with the compose Sync Gateway and Couchbase Server services
  available THE system SHALL execute the round-trip, guard-rejection and revision-conflict
  scenarios against those services over the Sync Gateway REST API.
- WHEN those services are not reachable THE system SHALL skip the integration suite cleanly with a
  message naming the compose command that starts them, and SHALL NOT fail the run.
- WHEN either `channels` or `_rev` is dropped anywhere in the read→modify→write path THE system
  SHALL fail the integration suite.
- WHEN a document is round-tripped THE system SHALL prove access preservation by a second Sync
  Gateway user subscribed to one of the document's channels still seeing the document afterward,
  rather than by asserting on the locally-held entity alone.
- WHEN the harness is configured THE system SHALL use the production Sync Gateway version, the
  production Couchbase Server version, shared bucket access, and the verbatim production sync
  function, so the test environment cannot pass on behavior production does not have.

### Story 4: Writes name the real acting actor (DATA-04)

As an auditor, I want `updatedBy` to identify who or what actually wrote a document, so that a
six-year-retained record can be attributed after the fact.

**Acceptance criteria**

- WHEN an API request writes a document THE system SHALL record the authenticated principal's id in
  `updatedBy`.
- WHEN a scheduled job writes a document THE system SHALL record the namespaced machine actor
  `system:{job_name}` in `updatedBy`.
- THE system SHALL NOT record a bare service name such as `"scheduler"` for any write.
- THE system SHALL NOT allow a machine actor to be shaped like a user id, so a machine write can
  never be mistaken for a human one.
- WHEN a repository write method is called THE system SHALL require the actor as an explicit
  parameter, so omitting it is a type error rather than a silent default.

## Out of scope

- **The lossless-envelope adapter refactor.** The root cause of Story 1 is that `valid_fields()`
  filtering discards *any* unrecognized persisted field, not just these two; generalizing the fix
  is filed as a follow-up issue so the gate can close on a narrow, reviewable change.
- **`updatedAtTzOffset` refresh parity on update.** The ancestor scheduler stamps a *server*-local
  offset on every update while `BaseOwnerEntity` here computes a *participant*-local offset at
  construction; "restoring parity" would regress the more correct behavior, so the disposition is
  recorded rather than acted on.
- **`CPAPSession` and `ProcessedSleep` domain coverage.** Neither type exists in this codebase; the
  consuming roadmap scopes their disposition to a later phase.
- **CI enforcement and branch protection for the new integration suite.** Making the round-trip test
  a required check is the durable anti-regression mechanism, but it is a repository-administration
  change tracked separately from this spec's code.
- **Any Couchbase Server or Sync Gateway version upgrade.** The harness pins the production
  versions deliberately; moving off them is a separate migration with its own compatibility work.
- **Retroactive repair of documents already written with `channels: null`.** This spec stops the
  bleeding; identifying and re-channeling damaged documents is a data-remediation task with a
  different risk profile.
