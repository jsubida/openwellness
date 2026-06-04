// MSW v2 request handlers + fixtures for the end-to-end login flow suite.
// The web analog of the mobile Ktor MockEngine handler set: every handler
// matches the FULL absolute URL the apiClient actually hits (built via
// buildApiUrl so the literal `:` verb survives), and returns the exact wire
// shapes the real backend sends.
import { http, HttpResponse } from 'msw'

import { buildApiUrl } from '@/core/api/url'
import { fakeJwt } from '@/test/jwt'

// --------------------------------------------------------------------------- //
// Token fixtures — fake JWTs carrying the role claims the UX gate decodes.
// --------------------------------------------------------------------------- //

/** Coach access token — passes the coach/admin role gate. */
export const coachToken = fakeJwt({
  sub: 'users/u1',
  roles: ['coach'],
  participant: null,
})

/** Participant access token — fails the role gate (NotAuthorized). */
export const participantToken = fakeJwt({
  sub: 'users/u2',
  roles: ['participant'],
  participant: 'participants/p2',
})

// --------------------------------------------------------------------------- //
// Wire-shape helpers
// --------------------------------------------------------------------------- //

/**
 * Exact-match URL matcher for a custom-method verb (e.g. `auth:verifyLoginCode`).
 *
 * MSW v2 parses a `:token` AFTER any path separator as a wildcard path
 * parameter — so a plain string `…/auth:sendLoginCode` would ALSO match
 * `…/auth:verifyLoginCode` (the colon delimits a param that matches any value).
 * We return an anchored RegExp with the colon escaped so each verb matches ONLY
 * its own URL. `buildApiUrl` produces the exact absolute URL the apiClient hits.
 */
export function apiUrl(verb: string): RegExp {
  const escaped = buildApiUrl(verb).replace(/[.*+?^${}()|[\]\\:]/g, '\\$&')
  return new RegExp(`^${escaped}$`)
}

/** A verify/refresh token-pair response body (TokenResponseDto / RefreshDto). */
export function tokenResponseBody(
  accessToken: string,
  refreshToken: string,
  principal: { userId: string; participant: string | null },
) {
  return {
    accessToken,
    tokenType: 'Bearer',
    expiresInSeconds: 900,
    refreshToken,
    principal,
  }
}

/** AIP-193 error envelope — the 400 shape the verify endpoint returns. */
export function aipError(code: number, status: string, message: string) {
  return HttpResponse.json(
    { error: { code, status, message } },
    { status: code },
  )
}

// --------------------------------------------------------------------------- //
// Default happy-path handlers (coach). Tests override per-case via
// server.use(...) inside the test body.
// --------------------------------------------------------------------------- //

const COACH_PRINCIPAL = { userId: 'users/u1', participant: null }

export const sendOk = () =>
  http.post(apiUrl('auth:sendLoginCode'), () =>
    HttpResponse.json({
      status: 'sent',
      message: 'Code sent.',
      expiresInSeconds: 900,
      resendAfterSeconds: 60,
    }),
  )

export const verifyOkCoach = () =>
  http.post(apiUrl('auth:verifyLoginCode'), () =>
    HttpResponse.json(
      tokenResponseBody(coachToken, 'refresh-1', COACH_PRINCIPAL),
    ),
  )

export const refreshOkCoach = () =>
  http.post(apiUrl('auth:refreshToken'), () =>
    HttpResponse.json(
      tokenResponseBody(coachToken, 'rotated-refresh', COACH_PRINCIPAL),
    ),
  )

export const revokeOk = () =>
  http.post(apiUrl('auth:revokeToken'), () =>
    HttpResponse.json({ status: 'revoked' }),
  )

/** The default handler set used to seed the server. */
export const defaultHandlers = [
  sendOk(),
  verifyOkCoach(),
  refreshOkCoach(),
  revokeOk(),
]
