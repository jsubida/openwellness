// Mirrors AuthError.kt (feature/auth/domain/AuthError.kt) plus web-only NotAuthorized

/**
 * Discriminated union of auth-domain failures.
 *
 * Variant names match the mobile sealed-class members exactly.
 * NotAuthorized is a web-only addition: role-gate rejection (user lacks
 * coach/admin access to this dashboard).
 * RateLimited carries retryAfterSeconds mirroring RateLimited(retryAfterSeconds: Long).
 * EmptyParticipant is intentionally omitted — it exists on mobile for the
 * registration flow only; the dashboard is login-only.
 */
export type AuthError =
  | { kind: 'InvalidEmail' }
  | { kind: 'InvalidCode' }
  | { kind: 'InvalidOrExpiredCode' }
  | { kind: 'RateLimited'; retryAfterSeconds: number }
  | { kind: 'Unauthorized' } // 401 — token absent, expired, or revoked; user must re-authenticate
  | { kind: 'NotAuthorized' } // role gate: signed in fine but lacks coach/admin access; web-only
  | { kind: 'NoInternet' }
  | { kind: 'Server' }
  | { kind: 'Unknown' }
