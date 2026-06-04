// Access-token claim decoding + role gating. No mobile mirror (mobile gates
// server-side); this is the dashboard's UX-only role gate. Claim keys match the
// backend JWT minted in auth/token_service.py (`sub`, `roles`). We base64url-
// decode the PAYLOAD segment only — NO signature verification: gating is UX,
// the server stays authoritative.

export interface AccessClaims {
  sub?: string
  roles: string[]
  [key: string]: unknown
}

/** Roles permitted into the coaching dashboard. */
export const ALLOWED_ROLES: readonly string[] = ['coach', 'admin']

/**
 * Decode the claims from a JWT's payload segment, or null if the token is
 * malformed/undecodable. A non-array `roles` claim is coerced to `[]` (matches
 * the backend's "malformed roles" guard, but degrades to empty instead of
 * throwing since this is purely a client UX gate).
 */
export function decodeAccessClaims(token: string): AccessClaims | null {
  const segments = token.split('.')
  if (segments.length !== 3) return null

  const payload = decodeBase64UrlJson(segments[1])
  if (payload == null || typeof payload !== 'object') return null

  const record = payload as Record<string, unknown>
  const roles = Array.isArray(record.roles) ? record.roles.map(String) : []
  const sub = typeof record.sub === 'string' ? record.sub : undefined

  return { ...record, sub, roles }
}

export function hasCoachOrAdminRole(claims: AccessClaims | null): boolean {
  if (claims == null) return false
  return claims.roles.some((role) => ALLOWED_ROLES.includes(role))
}

function decodeBase64UrlJson(segment: string): unknown {
  try {
    const base64 = segment.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    const decoded = atob(padded)
    return JSON.parse(decoded)
  } catch {
    return null
  }
}
