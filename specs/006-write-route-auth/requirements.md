# Requirements: Write-route authentication

Status: approved
Created: 2026-09-04

## Summary

OpenWellness currently derives write attribution from an unverified `X-Principal-Id` header and wires `require_principal` to zero routes, leaving 188 write-method routes able to accept unauthenticated writes and stamp `updatedBy="anonymous"`. This makes the `system:` machine-actor namespace forgeable. Under opserver's six-year HIPAA retention constraint, the audit field on an archive copy is the record read back years later. Traceability: this specification closes opserver DATA-04's authenticated-principal half and residual R-10.

## User stories

### Story 1: Authenticated writes

As a service operator, I want every write route to require a verified bearer principal, so that stored attribution cannot be forged.

**Acceptance criteria**

- WHEN an unauthenticated client calls a write route THE system SHALL return 401 and store nothing.
- WHEN a client supplies `X-Principal-Id` on a write THE system SHALL return 403 and store nothing.
- WHEN an authenticated client writes THE system SHALL attribute the repository operation to the bearer subject.

### Story 2: Preserve reads and bootstrap

As an API client, I want reads and authentication endpoints to remain reachable, so that existing clients can obtain credentials and continue reading data.

**Acceptance criteria**

- WHEN a client calls a read route THE system SHALL preserve its prior authentication behavior.
- WHEN a client calls one of the six authentication endpoints without a bearer THE system SHALL reach that endpoint rather than return a guard-generated 401 or 403.
- WHEN a write route is registered THE system SHALL be structurally proven guarded or explicitly exempt.

## Out of scope

- Vendor and Sync Gateway event handlers, which Phase 10 adds to the reviewed exemption list.
- Changes to token cryptography or the repository data model.

## Open questions

- None.