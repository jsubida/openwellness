# Requirements: Lossless persistence envelope

Status: draft
Created: 2026-08-14

## Summary

The Couchbase persistence boundary converts a stored document into a domain entity by filtering
the document through the entity's declared field set — `CBBaseEntity.to_domain` and
`CBBaseRepository.update_entity_valid_fields` both keep only what `entity_cls.valid_fields()`
returns. Any key the stored document carries that the domain dataclass does not declare is
**destroyed** on read, and the next write sends the document back without it. Spec 004 fixed two
instances of this — `channels` and `_rev` — by declaring them on `BaseEntity`. It did not fix the
mechanism, and the mechanism is what makes the next dropped field just as silent as the last one:
nothing in the stack raises, logs, or returns a non-2xx when a field disappears.

The generalizable principle this spec exists to establish: **the persistence boundary must
round-trip the full persisted representation losslessly, access metadata included.** A field the
datastore holds and the domain does not model is not noise to be discarded — it is state owned by
some other writer of the same bucket, and discarding it is a write to that writer's data.

This is the deferred root-cause follow-up to `specs/004-write-correctness/`, which recorded it
under "Out of scope" so the gate could close on a narrow, reviewable change.

## Motivating background

`spring` is a **shared** bucket. The legacy scheduler, the legacy Node api, mobile Couchbase Lite
replicas and this codebase all write the same documents. A field this codebase does not declare is
routinely a field another writer depends on, so "unrecognized" and "unused" are not the same
statement. The failure has no HTTP signal in either direction: Sync Gateway's deployed sync
function performs no document validation (no `requireUser`, no `access`, no validation block), so a
document that loses a field is accepted exactly like one that did not.

## User stories

### Story 1: An unmodelled persisted field survives a read-modify-write

As a maintainer of any service that shares the `spring` bucket, I want a field my service writes to
still be there after this codebase reads and rewrites the document, so that adding a field on my
side does not require a coordinated change here first.

**Acceptance criteria**

- WHEN a stored document carries a key the domain entity does not declare THE system SHALL retain
  that key and its value through the read → modify → write cycle.
- WHEN the domain entity declares a field that shadows a retained key THE system SHALL treat the
  declared field as authoritative, so declaring a field is how a value becomes owned rather than
  carried.
- WHEN a retained key would collide with adapter-internal metadata THE system SHALL resolve it
  deterministically and SHALL NOT silently prefer one.

### Story 2: Field loss is detectable rather than silent

As an operator, I want the boundary to be able to report that it dropped something, so that the
next instance of this class is found by a signal rather than by a participant noticing missing data
on a phone.

**Acceptance criteria**

- WHEN the boundary discards a persisted key THE system SHALL emit a record naming the document id,
  the document type, and the discarded key.
- WHEN the round-trip is exercised in tests THE system SHALL fail if any key present on read is
  absent on the outgoing write, rather than asserting only on the fields the test happens to name.

## Known instances of this class

These are recorded so the refactor is sized against the real surface rather than against the two
fields spec 004 happened to reach.

| Instance | Status | Notes |
|---|---|---|
| `channels` | fixed in 004 | Declared on `BaseEntity`. The failure mode: the sync function assigns `channel([doc.owner].concat(doc.channels \|\| []))`, so a null array collapses access to the owner and Sync Gateway pushes a channel *removal* to every other subscriber's replica. |
| `_rev` | fixed in 004 | Declared on `BaseEntity`. Dropping it turned every update into a blind write with no conflict detection. |
| `updatedAtTzOffset` | open, **envelope-level** | See below. |
| Every other unmodelled key on every shared document type | open, unenumerated | The point of this spec: the count is unknown precisely because the loss is silent. |

### `updatedAtTzOffset` — why the fix is envelope-level and not parity

The legacy scheduler stamps `updatedAtTzOffset` on **every update**, using a **server**-local UTC
offset (`schedulernew/common/infrastructure/cb_entity_repository.py:135`; the Node api does the
same at `couchbase-admin.js:190`). This codebase computes the offset **at construction** from the
**participant's** locale, on `BaseOwnerEntity`, and does not refresh it on update.

The tempting framing is "restore parity with the ancestor." That would be a regression: a
participant-local offset is the more correct value, and a server-local offset stamped by whichever
host ran the job is the less correct one. Neither is a lossless-round-trip question on its own — but
the reason the divergence is invisible today *is* the envelope: the field is not declared, so the
boundary cannot tell "this codebase deliberately did not refresh it" from "this codebase discarded
what the scheduler wrote." Fix the envelope first; the disposition of the value then becomes a
decision that can be made on evidence rather than an artifact of the filter.

### `CPAPSession` / `ProcessedSleep` — a separate disposition question, not part of this refactor

`CPAPSession` and `ProcessedSleep` exist in the legacy scheduler's `cpap` module with **no
equivalent domain type in this codebase**. That is a missing-type question, not a lossy-conversion
one: no entity here reads or rewrites those documents, so no envelope change affects them. It is
recorded here only so that a reader who arrives from the same investigation does not fold it into
this spec's scope. Its disposition is tracked by the consuming roadmap.

## Out of scope

- **Retroactive repair of documents already written with a field missing.** This spec stops the
  loss; identifying and restoring already-damaged documents is a data-remediation task with a
  different risk profile.
- **The Mongo and Postgres adapters**, unless the design finds the same filter shape there. The
  defect as observed is specific to the Couchbase `valid_fields()` filter.
- **Changing which fields the domain declares.** Declaring a field is how a value becomes *owned*;
  this spec is about what happens to values that are *not* owned.
- **Any change to the channels guard added by spec 004.** The guard is a permanent invariant, not
  migration scaffolding, and it stays whatever the envelope does.

## Open questions

- Where does the carried remainder live — an opaque dict on `BaseEntity`, a wrapper the adapter
  owns, or a merge performed at write time against a re-read document? The last reintroduces the
  read-before-write round trip spec 004's design deliberately avoided.
- How does the remainder interact with the `{type}Archived` copy convention, which POSTs a
  different document with no prior revision?
- Does the Postgres adapter's `dataclasses.asdict` path have the same shape, and if so does a
  single fix cover both, or do the two backends need different mechanisms?
