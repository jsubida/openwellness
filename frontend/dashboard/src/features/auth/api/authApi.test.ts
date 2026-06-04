// Integration tests for authApi.ts. Mirrors OpenWellnessAuthRepositoryTest.kt.
// Stubs fetch the same way apiClient.test.ts does (vi.stubGlobal).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { tokenStorage } from '@/core/auth/tokenStorage'
import {
  dataErrorToAuthError,
  refreshSession,
  revokeToken,
  sendLoginCode,
  verifyLoginCode,
} from './authApi'
import type { DataError } from '@/core/errors'

// --------------------------------------------------------------------------- //
// Helpers
// --------------------------------------------------------------------------- //
function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
}

const TOKEN_BODY = {
  accessToken: 'access-1',
  tokenType: 'Bearer',
  expiresInSeconds: 900,
  refreshToken: 'refresh-1',
  principal: { userId: 'u1', participant: 'participants/42' },
}

const SEND_BODY = {
  status: 'OK',
  message: 'Check your inbox.',
  expiresInSeconds: 300,
  resendAfterSeconds: 60,
}

const ERROR_400 = {
  error: {
    code: 400,
    status: 'INVALID_ARGUMENT',
    message: 'The code is invalid or has expired.',
    details: [],
  },
}

const ERROR_429_WITH_SECS = {
  error: {
    code: 429,
    status: 'RESOURCE_EXHAUSTED',
    message: 'Slow down.',
    details: [{ retry_after_secs: 42 }],
  },
}

const ERROR_429_NO_SECS = {
  error: {
    code: 429,
    status: 'RESOURCE_EXHAUSTED',
    message: 'Slow down.',
    details: [],
  },
}

const ERROR_401 = {
  error: {
    code: 401,
    status: 'UNAUTHENTICATED',
    message: 'Authentication required.',
  },
}

const ERROR_500 = {
  error: { code: 500, status: 'INTERNAL', message: 'Internal server error.' },
}

beforeEach(() => {
  tokenStorage.clear()
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

// --------------------------------------------------------------------------- //
// dataErrorToAuthError unit tests
// --------------------------------------------------------------------------- //
describe('dataErrorToAuthError', () => {
  it('maps BAD_REQUEST → InvalidOrExpiredCode', () => {
    const e: DataError = { kind: 'BAD_REQUEST' }
    expect(dataErrorToAuthError(e)).toEqual({ kind: 'InvalidOrExpiredCode' })
  })

  it('maps TOO_MANY_REQUESTS with retryAfterSeconds → RateLimited(n)', () => {
    const e: DataError = { kind: 'TOO_MANY_REQUESTS', retryAfterSeconds: 42 }
    expect(dataErrorToAuthError(e)).toEqual({
      kind: 'RateLimited',
      retryAfterSeconds: 42,
    })
  })

  it('maps TOO_MANY_REQUESTS without retryAfterSeconds → RateLimited(60)', () => {
    const e: DataError = { kind: 'TOO_MANY_REQUESTS' }
    expect(dataErrorToAuthError(e)).toEqual({
      kind: 'RateLimited',
      retryAfterSeconds: 60,
    })
  })

  it('maps UNAUTHORIZED → Unauthorized', () => {
    expect(dataErrorToAuthError({ kind: 'UNAUTHORIZED' })).toEqual({
      kind: 'Unauthorized',
    })
  })

  it('maps NO_INTERNET → NoInternet', () => {
    expect(dataErrorToAuthError({ kind: 'NO_INTERNET' })).toEqual({
      kind: 'NoInternet',
    })
  })

  it('maps SERVER_ERROR → Server', () => {
    expect(dataErrorToAuthError({ kind: 'SERVER_ERROR' })).toEqual({
      kind: 'Server',
    })
  })

  it('maps SERVICE_UNAVAILABLE → Server', () => {
    expect(dataErrorToAuthError({ kind: 'SERVICE_UNAVAILABLE' })).toEqual({
      kind: 'Server',
    })
  })

  it('maps any other kind → Unknown', () => {
    expect(dataErrorToAuthError({ kind: 'NOT_FOUND' })).toEqual({
      kind: 'Unknown',
    })
    expect(dataErrorToAuthError({ kind: 'CONFLICT' })).toEqual({
      kind: 'Unknown',
    })
    expect(dataErrorToAuthError({ kind: 'UNKNOWN' })).toEqual({
      kind: 'Unknown',
    })
    expect(dataErrorToAuthError({ kind: 'SERIALIZATION' })).toEqual({
      kind: 'Unknown',
    })
  })
})

// --------------------------------------------------------------------------- //
// sendLoginCode
// --------------------------------------------------------------------------- //
describe('sendLoginCode', () => {
  it('returns ok(SendCodeResult) on 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(SEND_BODY)),
    )
    const result = await sendLoginCode('person@example.com')
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.value).toEqual({
        expiresInSeconds: 300,
        resendAfterSeconds: 60,
        message: 'Check your inbox.',
      })
    }
  })

  it('returns err(RateLimited(42)) on 429 with body retry_after_secs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_429_WITH_SECS, 429)),
    )
    const result = await sendLoginCode('person@example.com')
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toEqual({
        kind: 'RateLimited',
        retryAfterSeconds: 42,
      })
    }
  })

  it('returns err(RateLimited(30)) on 429 with only Retry-After header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(ERROR_429_NO_SECS, 429, { 'Retry-After': '30' }),
      ),
    )
    const result = await sendLoginCode('person@example.com')
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toEqual({
        kind: 'RateLimited',
        retryAfterSeconds: 30,
      })
    }
  })

  it('returns err(RateLimited(60)) on 429 with neither body secs nor header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_429_NO_SECS, 429)),
    )
    const result = await sendLoginCode('person@example.com')
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toEqual({
        kind: 'RateLimited',
        retryAfterSeconds: 60,
      })
    }
  })

  it('returns err(NoInternet) on fetch TypeError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    const result = await sendLoginCode('person@example.com')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'NoInternet' })
  })

  it('returns err(Server) on 500', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_500, 500)),
    )
    const result = await sendLoginCode('person@example.com')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'Server' })
  })
})

// --------------------------------------------------------------------------- //
// verifyLoginCode
// --------------------------------------------------------------------------- //
describe('verifyLoginCode', () => {
  it('returns ok(AuthSession) on 200 with all fields mapped', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(TOKEN_BODY)),
    )
    const result = await verifyLoginCode('person@example.com', '123456')
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.value).toEqual({
        tokens: {
          accessToken: 'access-1',
          tokenType: 'Bearer',
          expiresInSeconds: 900,
          refreshToken: 'refresh-1',
        },
        principal: {
          userId: 'u1',
          participant: 'participants/42',
        },
      })
    }
  })

  it('returns err(InvalidOrExpiredCode) on 400', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_400, 400)),
    )
    const result = await verifyLoginCode('person@example.com', '000000')
    expect(result.ok).toBe(false)
    if (!result.ok)
      expect(result.error).toEqual({ kind: 'InvalidOrExpiredCode' })
  })

  it('returns err(Unauthorized) on 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_401, 401)),
    )
    const result = await verifyLoginCode('person@example.com', '123456')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'Unauthorized' })
  })

  it('returns err(NoInternet) on fetch TypeError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Network error')
      }),
    )
    const result = await verifyLoginCode('person@example.com', '123456')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'NoInternet' })
  })

  it('returns err(Server) on 500', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_500, 500)),
    )
    const result = await verifyLoginCode('person@example.com', '123456')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'Server' })
  })
})

// --------------------------------------------------------------------------- //
// revokeToken — must attach Authorization header (auth: true)
// --------------------------------------------------------------------------- //
describe('revokeToken', () => {
  it('sends the Authorization: Bearer header', async () => {
    tokenStorage.setTokens({
      accessToken: 'my-access',
      refreshToken: 'my-refresh',
    })

    let capturedAuth: string | null = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        capturedAuth = new Headers(init?.headers).get('Authorization')
        return jsonResponse({ status: 'OK' })
      }),
    )

    const result = await revokeToken('my-refresh')
    expect(result.ok).toBe(true)
    expect(capturedAuth).toBe('Bearer my-access')
  })

  it('returns ok(void) on 200', async () => {
    tokenStorage.setTokens({ accessToken: 'acc', refreshToken: 'ref' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ status: 'OK' })),
    )
    const result = await revokeToken('ref')
    expect(result.ok).toBe(true)
  })

  it('returns err(Unauthorized) on 401', async () => {
    tokenStorage.setTokens({ accessToken: 'acc', refreshToken: 'ref' })
    // Stub both the initial request and any refresh attempt as 401.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_401, 401)),
    )
    const result = await revokeToken('ref')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'Unauthorized' })
  })

  it('returns err(Server) on 500', async () => {
    tokenStorage.setTokens({ accessToken: 'acc', refreshToken: 'ref' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ERROR_500, 500)),
    )
    const result = await revokeToken('ref')
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'Server' })
  })
})

// --------------------------------------------------------------------------- //
// refreshSession
// --------------------------------------------------------------------------- //
describe('refreshSession', () => {
  it('returns ok and persists rotated pair on 200', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    const rotated = {
      accessToken: 'new-access',
      tokenType: 'Bearer',
      expiresInSeconds: 900,
      refreshToken: 'new-refresh',
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(rotated)),
    )

    const result = await refreshSession()
    expect(result.ok).toBe(true)
    expect(tokenStorage.getAccessToken()).toBe('new-access')
    expect(tokenStorage.getRefreshToken()).toBe('new-refresh')
  })

  it('returns err(Unauthorized) and makes zero fetch calls when no refresh token', async () => {
    // tokenStorage already cleared in beforeEach
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const result = await refreshSession()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error).toEqual({ kind: 'Unauthorized' })
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
