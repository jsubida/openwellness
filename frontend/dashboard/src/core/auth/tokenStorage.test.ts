// Tests for core/auth/tokenStorage.ts (in-memory access + persisted refresh).
import { describe, it, expect, beforeEach } from 'vitest'

import { tokenStorage } from './tokenStorage'

const REFRESH_KEY = 'openwellness.refreshToken'

beforeEach(() => {
  tokenStorage.clear()
  localStorage.clear()
})

describe('tokenStorage', () => {
  it('returns null for both tokens initially', () => {
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('keeps the access token in memory only — never in localStorage', () => {
    tokenStorage.setTokens({
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    })
    expect(tokenStorage.getAccessToken()).toBe('access-1')
    // The access token must NOT be discoverable anywhere in localStorage.
    const dump = JSON.stringify({ ...localStorage })
    expect(dump).not.toContain('access-1')
  })

  it('persists the refresh token in localStorage under the documented key', () => {
    tokenStorage.setTokens({
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    })
    expect(tokenStorage.getRefreshToken()).toBe('refresh-1')
    expect(localStorage.getItem(REFRESH_KEY)).toBe('refresh-1')
  })

  it('reads a refresh token persisted across a reload (fresh module memory)', () => {
    localStorage.setItem(REFRESH_KEY, 'persisted-refresh')
    expect(tokenStorage.getRefreshToken()).toBe('persisted-refresh')
  })

  it('clear() removes both tokens', () => {
    tokenStorage.setTokens({
      accessToken: 'access-1',
      refreshToken: 'refresh-1',
    })
    tokenStorage.clear()
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull()
  })
})
