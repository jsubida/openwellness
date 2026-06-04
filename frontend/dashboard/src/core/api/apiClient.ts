// Authenticated HTTP client. Mirrors mobile HttpClientFactory.kt: a bearer-auth
// request path plus a SEPARATE non-intercepted refresh path (the recursion
// guard — a refresh can never itself trigger a refresh). The refresh is a
// single-flight rotating refresh: N concurrent 401s share ONE network call.

import { tokenStorage } from '../auth/tokenStorage'
import type { DataError } from '../errors'
import { parseRetryAfterSeconds, statusToNetworkError } from '../errors'
import type { EmptyResult, Result } from '../result'
import { err, ok, okVoid } from '../result'
import { buildApiUrl } from './url'

export interface RequestOptions {
  method?: string
  body?: unknown
  /** Attach `Authorization: Bearer <access>` when true and a token exists. */
  auth?: boolean
  signal?: AbortSignal
}

/** Wire shape of the refresh response (camelCase). Mirrors RefreshDtos.kt. */
interface RefreshResponseDto {
  accessToken: string
  tokenType: string
  expiresInSeconds: number
  refreshToken: string
}

const REFRESH_PATH = 'auth:refreshToken'

// Single in-flight refresh shared by all concurrent callers (single-flight).
let refreshInFlight: Promise<EmptyResult<DataError>> | null = null

// Invoked once when the session is cleared (refresh failed / family revoked).
let onSessionCleared: (() => void) | null = null

export function setOnSessionCleared(cb: (() => void) | null): void {
  onSessionCleared = cb
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<Result<T, DataError>> {
  const first = await rawRequest(path, options)
  if (!first.ok) return first

  const response = first.value
  // 401 interceptor: only for authenticated requests. Refresh once, then
  // retry the original request ONCE with the rotated access token.
  if (response.status === 401 && options.auth) {
    const refreshed = await refreshOnce()
    if (!refreshed.ok) return err({ kind: 'UNAUTHORIZED' })

    const retry = await rawRequest(path, options)
    if (!retry.ok) return retry
    // A second 401 means the new token is also rejected — no second refresh.
    if (retry.value.status === 401) return err({ kind: 'UNAUTHORIZED' })
    return interpret<T>(retry.value)
  }

  return interpret<T>(response)
}

/**
 * Single-flight rotating refresh. Concurrent callers await the same promise.
 * No stored refresh token → UNAUTHORIZED with NO network call. On success the
 * rotated pair is persisted BEFORE resolving; on failure storage is cleared and
 * `onSessionCleared` fires.
 */
export function refreshOnce(): Promise<EmptyResult<DataError>> {
  if (refreshInFlight) return refreshInFlight

  refreshInFlight = doRefresh().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

async function doRefresh(): Promise<EmptyResult<DataError>> {
  const storedRefresh = tokenStorage.getRefreshToken()
  if (storedRefresh == null) return err({ kind: 'UNAUTHORIZED' })

  // Non-intercepted plain fetch (auth omitted) — cannot recurse into refresh.
  const raw = await rawRequest(REFRESH_PATH, {
    method: 'POST',
    body: { refreshToken: storedRefresh },
  })
  if (!raw.ok) {
    // Network failure (e.g. NO_INTERNET). Don't nuke the session — let the
    // caller surface the transport error and let a later attempt retry.
    return err(raw.error)
  }

  const response = raw.value
  if (response.status >= 200 && response.status <= 299) {
    try {
      const body = (await response.json()) as RefreshResponseDto
      tokenStorage.setTokens({
        accessToken: body.accessToken,
        refreshToken: body.refreshToken,
      })
      return okVoid()
    } catch {
      // A 2xx with an unparseable body is effectively a failed refresh.
    }
  }

  clearSession()
  return err({ kind: 'UNAUTHORIZED' })
}

function clearSession(): void {
  tokenStorage.clear()
  onSessionCleared?.()
}

/**
 * Perform the fetch and return the raw Response (or a transport DataError).
 * Status interpretation happens in `interpret` so the 401 interceptor can act
 * on the raw status first.
 */
async function rawRequest(
  path: string,
  options: RequestOptions,
): Promise<Result<Response, DataError>> {
  const headers: Record<string, string> = {}
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (options.auth) {
    const access = tokenStorage.getAccessToken()
    if (access != null) headers.Authorization = `Bearer ${access}`
  }

  try {
    const response = await fetch(buildApiUrl(path), {
      method: options.method ?? 'POST',
      headers,
      body:
        options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    })
    return ok(response)
  } catch (e) {
    // fetch rejects with TypeError on network failure / DNS / CORS.
    if (e instanceof TypeError) return err({ kind: 'NO_INTERNET' })
    return err({ kind: 'UNKNOWN' })
  }
}

/** Map a completed Response to a typed Result<T, DataError>. */
async function interpret<T>(response: Response): Promise<Result<T, DataError>> {
  if (response.status >= 200 && response.status <= 299) {
    try {
      return ok((await response.json()) as T)
    } catch {
      return err({ kind: 'SERIALIZATION' })
    }
  }

  if (response.status === 429) {
    return err({
      kind: 'TOO_MANY_REQUESTS',
      retryAfterSeconds: await parseRetryAfterSeconds(response),
    })
  }

  return err({ kind: statusToNetworkError(response.status) })
}
