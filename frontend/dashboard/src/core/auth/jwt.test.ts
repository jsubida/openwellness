// Tests for core/auth/jwt.ts (access-token claim decoding + role gating).
import { describe, it, expect } from 'vitest'

import { decodeAccessClaims, hasCoachOrAdminRole } from './jwt'

// base64url-encode a UTF-8 string (no padding) the way a real JWT segment is.
function b64url(value: string): string {
  return btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

// Build a fake (unsigned-style) JWT: header.payload.signature.
function fakeJwt(payload: Record<string, unknown>): string {
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = b64url(JSON.stringify(payload))
  return `${header}.${body}.fakesignature`
}

describe('decodeAccessClaims', () => {
  it('extracts sub and roles from a valid token', () => {
    const token = fakeJwt({ sub: 'user-1', roles: ['coach'] })
    const claims = decodeAccessClaims(token)
    expect(claims).not.toBeNull()
    expect(claims?.sub).toBe('user-1')
    expect(claims?.roles).toEqual(['coach'])
  })

  it('returns null for a malformed token', () => {
    expect(decodeAccessClaims('not-a-jwt')).toBeNull()
    expect(decodeAccessClaims('')).toBeNull()
    expect(decodeAccessClaims('a.b')).toBeNull()
    expect(decodeAccessClaims('a.%%%.c')).toBeNull()
  })

  it('coerces a non-array roles claim to an empty array', () => {
    const token = fakeJwt({ sub: 'user-1', roles: 'coach' })
    const claims = decodeAccessClaims(token)
    expect(claims?.roles).toEqual([])
  })

  it('coerces a missing roles claim to an empty array', () => {
    const token = fakeJwt({ sub: 'user-1' })
    const claims = decodeAccessClaims(token)
    expect(claims?.roles).toEqual([])
  })
})

describe('hasCoachOrAdminRole', () => {
  it('is true for a coach', () => {
    expect(hasCoachOrAdminRole({ roles: ['coach'] })).toBe(true)
  })

  it('is true for an admin', () => {
    expect(hasCoachOrAdminRole({ roles: ['admin'] })).toBe(true)
  })

  it('is false for a participant', () => {
    expect(hasCoachOrAdminRole({ roles: ['participant'] })).toBe(false)
  })

  it('is false for empty roles', () => {
    expect(hasCoachOrAdminRole({ roles: [] })).toBe(false)
  })

  it('is false for null claims', () => {
    expect(hasCoachOrAdminRole(null)).toBe(false)
  })
})
