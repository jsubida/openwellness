// Tests for core/api/apiClient.ts (auth bearer + single-flight rotating refresh).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { tokenStorage } from '../auth/tokenStorage'
import { request, refreshOnce, setOnSessionCleared } from './apiClient'

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

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.toString()
  return (input as Request).url
}

const REFRESH_BODY = {
  accessToken: 'new-access',
  tokenType: 'Bearer',
  expiresInSeconds: 900,
  refreshToken: 'new-refresh',
}

beforeEach(() => {
  tokenStorage.clear()
  localStorage.clear()
  setOnSessionCleared(null)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('request — success and transport errors', () => {
  it('returns ok with the parsed JSON body on 2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ hello: 'world' })),
    )
    const result = await request<{ hello: string }>('auth:sendLoginCode', {
      body: {},
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.value).toEqual({ hello: 'world' })
  })

  it('maps a fetch TypeError to NO_INTERNET', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch')
      }),
    )
    const result = await request('auth:sendLoginCode', { body: {} })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('NO_INTERNET')
  })

  it('maps a JSON parse failure on a 2xx to SERIALIZATION', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('not json', { status: 200 })),
    )
    const result = await request('auth:sendLoginCode', { body: {} })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('SERIALIZATION')
  })

  it('maps a 429 to TOO_MANY_REQUESTS with the parsed retryAfterSeconds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            error: {
              code: 429,
              status: 'RESOURCE_EXHAUSTED',
              message: 'slow down',
              details: [{ retry_after_secs: 42 }],
            },
          },
          429,
        ),
      ),
    )
    const result = await request('auth:sendLoginCode', { body: {} })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error.kind).toBe('TOO_MANY_REQUESTS')
      expect(result.error.retryAfterSeconds).toBe(42)
    }
  })

  it('maps other non-2xx via statusToNetworkError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({}, 404)),
    )
    const result = await request('auth:sendLoginCode', { body: {} })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('NOT_FOUND')
  })
})

describe('request — 401 interceptor for auth requests', () => {
  it('refreshes once, retries with the new token, and returns ok', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    const calls: string[] = []
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = urlOf(input)
        if (url.endsWith('auth:refreshToken')) {
          calls.push('refresh')
          return jsonResponse(REFRESH_BODY)
        }
        calls.push('protected')
        // First protected call 401s; the retry (with new token) succeeds.
        const auth = (init?.headers as Record<string, string>)?.Authorization
        if (auth === 'Bearer new-access') return jsonResponse({ data: 'ok' })
        return jsonResponse({}, 401)
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await request<{ data: string }>('me:get', {
      method: 'GET',
      auth: true,
    })
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.value).toEqual({ data: 'ok' })
    expect(calls).toEqual(['protected', 'refresh', 'protected'])
  })

  it('returns UNAUTHORIZED if the retry 401s again (no second refresh)', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    let refreshCalls = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = urlOf(input)
      if (url.endsWith('auth:refreshToken')) {
        refreshCalls += 1
        return jsonResponse(REFRESH_BODY)
      }
      return jsonResponse({}, 401)
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await request('me:get', { method: 'GET', auth: true })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('UNAUTHORIZED')
    expect(refreshCalls).toBe(1)
  })

  it('returns UNAUTHORIZED when the refresh itself fails', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = urlOf(input)
      if (url.endsWith('auth:refreshToken')) return jsonResponse({}, 401)
      return jsonResponse({}, 401)
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await request('me:get', { method: 'GET', auth: true })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('UNAUTHORIZED')
  })

  it('does NOT intercept 401 for non-auth requests', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    let refreshCalls = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = urlOf(input)
      if (url.endsWith('auth:refreshToken')) refreshCalls += 1
      return jsonResponse({}, 401)
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await request('auth:verifyLoginCode', { body: {} })
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('UNAUTHORIZED')
    expect(refreshCalls).toBe(0)
  })
})

describe('refreshOnce — single-flight rotating refresh', () => {
  it('shares ONE network call across two concurrent 401-ing auth requests', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    let refreshCalls = 0
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = urlOf(input)
        if (url.endsWith('auth:refreshToken')) {
          refreshCalls += 1
          // Slow refresh so both requests overlap on the in-flight promise.
          await new Promise((r) => setTimeout(r, 10))
          return jsonResponse(REFRESH_BODY)
        }
        const auth = (init?.headers as Record<string, string>)?.Authorization
        if (auth === 'Bearer new-access') return jsonResponse({ data: 'ok' })
        return jsonResponse({}, 401)
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    const [a, b] = await Promise.all([
      request<{ data: string }>('me:get', { method: 'GET', auth: true }),
      request<{ data: string }>('teams:list', { method: 'GET', auth: true }),
    ])
    expect(a.ok).toBe(true)
    expect(b.ok).toBe(true)
    expect(refreshCalls).toBe(1)
  })

  it('persists the rotated token pair after a successful refresh', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(REFRESH_BODY)),
    )

    const result = await refreshOnce()
    expect(result.ok).toBe(true)
    expect(tokenStorage.getAccessToken()).toBe('new-access')
    expect(tokenStorage.getRefreshToken()).toBe('new-refresh')
  })

  it('clears storage and invokes onSessionCleared on refresh failure', async () => {
    tokenStorage.setTokens({
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    })
    const onCleared = vi.fn()
    setOnSessionCleared(onCleared)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({}, 401)),
    )

    const result = await refreshOnce()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('UNAUTHORIZED')
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
    expect(onCleared).toHaveBeenCalledTimes(1)
  })

  it('returns UNAUTHORIZED with ZERO network calls when no refresh token is stored', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(REFRESH_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const result = await refreshOnce()
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.error.kind).toBe('UNAUTHORIZED')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
