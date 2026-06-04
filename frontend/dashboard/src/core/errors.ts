// Transport-level error kinds + status mapping + Retry-After parsing.
// Mirrors mobile DataError.kt (the `DataError.Network` enum), HttpClientExt.kt
// (`statusToNetworkError`), and KtorAuthRemoteDataSource.parseRetryAfterSeconds.

import type { ErrorEnvelope } from './api/types'

/**
 * String-literal union mirroring `DataError.Network` 1:1 (same names). 400
 * (BAD_REQUEST) matters for the auth surface: verify endpoints return 400 for
 * an invalid/expired OTP code.
 */
export type NetworkErrorKind =
  | 'BAD_REQUEST'
  | 'REQUEST_TIMEOUT'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'TOO_MANY_REQUESTS'
  | 'NO_INTERNET'
  | 'PAYLOAD_TOO_LARGE'
  | 'SERVER_ERROR'
  | 'SERVICE_UNAVAILABLE'
  | 'SERIALIZATION'
  | 'UNKNOWN'

export interface DataError {
  kind: NetworkErrorKind
  /** Populated only for TOO_MANY_REQUESTS (429). */
  retryAfterSeconds?: number
}

const DEFAULT_RETRY_AFTER_SECONDS = 60

/**
 * Maps a non-2xx HTTP status to a kind. Same table as HttpClientExt.kt
 * `statusToNetworkError`: explicit 400/401/403/404/408/409/413/429/503, any
 * other 5xx → SERVER_ERROR, everything else → UNKNOWN.
 */
export function statusToNetworkError(status: number): NetworkErrorKind {
  switch (status) {
    case 400:
      return 'BAD_REQUEST'
    case 401:
      return 'UNAUTHORIZED'
    case 403:
      return 'FORBIDDEN'
    case 404:
      return 'NOT_FOUND'
    case 408:
      return 'REQUEST_TIMEOUT'
    case 409:
      return 'CONFLICT'
    case 413:
      return 'PAYLOAD_TOO_LARGE'
    case 429:
      return 'TOO_MANY_REQUESTS'
    case 503:
      return 'SERVICE_UNAVAILABLE'
    default:
      if (status >= 500 && status <= 599) return 'SERVER_ERROR'
      return 'UNKNOWN'
  }
}

/**
 * Resolve the rate-limit backoff for a 429. Precedence mirrors the mobile
 * `parseRetryAfterSeconds`: body `error.details[].retry_after_secs` (first
 * detail that has it) → `Retry-After` header → default 60.
 *
 * Reads `response.clone()` so the caller can still consume the original body.
 * Tolerates a non-JSON body (falls through to the header/default).
 */
export async function parseRetryAfterSeconds(
  response: Response,
): Promise<number> {
  const fromBody = await retryAfterFromBody(response)
  if (fromBody != null) return fromBody

  const header = response.headers.get('Retry-After')
  const fromHeader = header != null ? Number.parseInt(header, 10) : NaN
  if (Number.isFinite(fromHeader)) return fromHeader

  return DEFAULT_RETRY_AFTER_SECONDS
}

async function retryAfterFromBody(response: Response): Promise<number | null> {
  try {
    const envelope = (await response.clone().json()) as ErrorEnvelope
    const details = envelope?.error?.details
    if (!Array.isArray(details)) return null
    for (const detail of details) {
      const secs = detail?.retry_after_secs
      if (typeof secs === 'number' && Number.isFinite(secs)) return secs
    }
    return null
  } catch {
    return null
  }
}
