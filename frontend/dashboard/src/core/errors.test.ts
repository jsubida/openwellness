// Tests for core/errors.ts (mirrors DataError.kt + HttpClientExt.kt + parseRetryAfterSeconds).
import { describe, it, expect } from 'vitest'

import { parseRetryAfterSeconds, statusToNetworkError } from './errors'

function jsonResponse(body: unknown, init?: ResponseInit): Response {
  return new Response(JSON.stringify(body), {
    status: 429,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('statusToNetworkError', () => {
  it('maps each known status to its kind', () => {
    expect(statusToNetworkError(400)).toBe('BAD_REQUEST')
    expect(statusToNetworkError(401)).toBe('UNAUTHORIZED')
    expect(statusToNetworkError(403)).toBe('FORBIDDEN')
    expect(statusToNetworkError(404)).toBe('NOT_FOUND')
    expect(statusToNetworkError(408)).toBe('REQUEST_TIMEOUT')
    expect(statusToNetworkError(409)).toBe('CONFLICT')
    expect(statusToNetworkError(413)).toBe('PAYLOAD_TOO_LARGE')
    expect(statusToNetworkError(429)).toBe('TOO_MANY_REQUESTS')
    expect(statusToNetworkError(503)).toBe('SERVICE_UNAVAILABLE')
  })

  it('maps any other 5xx to SERVER_ERROR', () => {
    expect(statusToNetworkError(500)).toBe('SERVER_ERROR')
    expect(statusToNetworkError(502)).toBe('SERVER_ERROR')
    expect(statusToNetworkError(599)).toBe('SERVER_ERROR')
  })

  it('falls back to UNKNOWN for unmapped statuses', () => {
    expect(statusToNetworkError(418)).toBe('UNKNOWN')
    expect(statusToNetworkError(302)).toBe('UNKNOWN')
  })
})

describe('parseRetryAfterSeconds', () => {
  it('prefers the body detail retry_after_secs over the header', async () => {
    const resp = jsonResponse(
      {
        error: {
          code: 429,
          status: 'RESOURCE_EXHAUSTED',
          message: 'slow down',
          details: [{ retry_after_secs: 42 }],
        },
      },
      { headers: { 'Content-Type': 'application/json', 'Retry-After': '30' } },
    )
    expect(await parseRetryAfterSeconds(resp)).toBe(42)
  })

  it('uses the first detail that carries retry_after_secs', async () => {
    const resp = jsonResponse({
      error: {
        code: 429,
        status: 'RESOURCE_EXHAUSTED',
        message: 'slow down',
        details: [{ foo: 'bar' }, { retry_after_secs: 7 }],
      },
    })
    expect(await parseRetryAfterSeconds(resp)).toBe(7)
  })

  it('falls back to the Retry-After header when the body lacks it', async () => {
    const resp = jsonResponse(
      {
        error: {
          code: 429,
          status: 'RESOURCE_EXHAUSTED',
          message: 'slow down',
          details: [],
        },
      },
      { headers: { 'Content-Type': 'application/json', 'Retry-After': '30' } },
    )
    expect(await parseRetryAfterSeconds(resp)).toBe(30)
  })

  it('defaults to 60 when neither body nor header carry a value', async () => {
    const resp = jsonResponse({
      error: {
        code: 429,
        status: 'RESOURCE_EXHAUSTED',
        message: 'slow down',
        details: [],
      },
    })
    expect(await parseRetryAfterSeconds(resp)).toBe(60)
  })

  it('tolerates a non-JSON body and falls back to header', async () => {
    const resp = new Response('not json', {
      status: 429,
      headers: { 'Retry-After': '15' },
    })
    expect(await parseRetryAfterSeconds(resp)).toBe(15)
  })

  it('tolerates a non-JSON body with no header and defaults to 60', async () => {
    const resp = new Response('not json', { status: 429 })
    expect(await parseRetryAfterSeconds(resp)).toBe(60)
  })

  it('does not consume the response body (clones before reading)', async () => {
    const resp = jsonResponse({
      error: {
        code: 429,
        status: 'RESOURCE_EXHAUSTED',
        message: 'slow down',
        details: [{ retry_after_secs: 5 }],
      },
    })
    await parseRetryAfterSeconds(resp)
    // Body must still be readable by the caller after parsing.
    expect(resp.bodyUsed).toBe(false)
    const body = await resp.json()
    expect(body.error.details[0].retry_after_secs).toBe(5)
  })
})
