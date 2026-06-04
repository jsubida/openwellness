// Tests for core/auth/AuthContext.tsx (bootstrap, sign-in/out, role gating).
// Fetch is stubbed via vi.stubGlobal (same pattern as core/api/apiClient.test);
// fake JWTs are built as base64url(header).base64url(payload).sig like jwt.test.
import { StrictMode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { refreshOnce, setOnSessionCleared } from '../api/apiClient'
import { AuthProvider, useAuth } from './AuthContext'
import { tokenStorage } from './tokenStorage'

// base64url-encode a UTF-8 string (no padding), the way a real JWT segment is.
function b64url(value: string): string {
  return btoa(value).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

// Build a fake (unsigned-style) JWT: header.payload.signature.
function fakeJwt(payload: Record<string, unknown>): string {
  const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = b64url(JSON.stringify(payload))
  return `${header}.${body}.fakesignature`
}

function refreshBody(accessToken: string, refreshToken = 'rotated-refresh') {
  return {
    accessToken,
    tokenType: 'Bearer',
    expiresInSeconds: 900,
    refreshToken,
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// Probe that renders the live auth status + userId + participant, plus a sign-out trigger.
function Probe() {
  const { status, session, signOut } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="userId">{session?.userId ?? '∅'}</span>
      <span data-testid="participant">{session?.participant ?? '∅'}</span>
      <button onClick={() => void signOut()}>Sign out</button>
    </div>
  )
}

function renderWithProvider(
  revokeSession?: (refreshToken: string) => Promise<unknown>,
) {
  return render(
    <AuthProvider revokeSession={revokeSession}>
      <Probe />
    </AuthProvider>,
  )
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

describe('AuthProvider — bootstrap', () => {
  it('ends unauthenticated with ZERO fetch calls when no refresh token is stored', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    renderWithProvider()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('authenticates a coach after a successful refresh and exposes the userId', async () => {
    tokenStorage.setTokens({
      accessToken: 'stale-access',
      refreshToken: 'stored-refresh',
    })
    // JWT carries bare participant id "p7"; SessionInfo must normalise to resource name.
    const access = fakeJwt({
      sub: 'users/u1',
      roles: ['coach'],
      participant: 'p7',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(refreshBody(access))),
    )

    renderWithProvider()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated'),
    )
    expect(screen.getByTestId('userId')).toHaveTextContent('users/u1')
    expect(screen.getByTestId('participant')).toHaveTextContent(
      'participants/p7',
    )
  })

  it('clears storage and stays unauthenticated when the role gate fails', async () => {
    tokenStorage.setTokens({
      accessToken: 'stale-access',
      refreshToken: 'stored-refresh',
    })
    const access = fakeJwt({ sub: 'users/u1', roles: ['participant'] })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(refreshBody(access))),
    )

    renderWithProvider()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('ends unauthenticated and clears storage when the refresh request fails (401)', async () => {
    tokenStorage.setTokens({
      accessToken: 'stale-access',
      refreshToken: 'stored-refresh',
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({}, 401)),
    )

    renderWithProvider()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    // refreshOnce clears storage on a 401 refresh — confirm both are gone.
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('reaches authenticated under StrictMode with a single shared refresh call', async () => {
    // Regression guard: StrictMode mounts → cleans up → remounts. A
    // bootstrapped-once ref would let the in-flight refresh from mount #1 bail
    // (cancelled) while mount #2 early-returns, hanging on 'loading' forever.
    // The single in-flight refresh must be SHARED across the double-mount, and
    // mount #2's (live) closure must apply the resulting state.
    tokenStorage.setTokens({
      accessToken: 'stale-access',
      refreshToken: 'stored-refresh',
    })
    const access = fakeJwt({ sub: 'users/u1', roles: ['coach'] })
    const fetchMock = vi.fn(async () => jsonResponse(refreshBody(access)))
    vi.stubGlobal('fetch', fetchMock)

    render(
      <StrictMode>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </StrictMode>,
    )

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated'),
    )
    expect(screen.getByTestId('userId')).toHaveTextContent('users/u1')
    // Single-flight: the double-mount shares ONE network refresh.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('AuthProvider — signOut', () => {
  it('revokes with the refresh token, clears storage, and goes unauthenticated', async () => {
    // Authenticate first via a successful bootstrap refresh.
    tokenStorage.setTokens({
      accessToken: 'stale-access',
      refreshToken: 'stored-refresh',
    })
    const access = fakeJwt({ sub: 'users/u1', roles: ['coach'] })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(refreshBody(access, 'rotated-refresh'))),
    )
    const revokeSession = vi.fn(async () => undefined)

    renderWithProvider(revokeSession)

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated'),
    )

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(revokeSession).toHaveBeenCalledTimes(1)
    // The rotated refresh (persisted by the bootstrap refresh) is what's sent.
    expect(revokeSession).toHaveBeenCalledWith('rotated-refresh')
    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })
})

describe('AuthProvider — mid-session session clearing', () => {
  it('flips to unauthenticated when the apiClient clears the session', async () => {
    // Bootstrap to authenticated with a coach token.
    tokenStorage.setTokens({
      accessToken: 'stale-access',
      refreshToken: 'stored-refresh',
    })
    const access = fakeJwt({ sub: 'users/u1', roles: ['coach'] })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(refreshBody(access)))
      // The NEXT refresh 401s → apiClient clears storage + fires the callback.
      .mockResolvedValueOnce(jsonResponse({}, 401))
    vi.stubGlobal('fetch', fetchMock)

    renderWithProvider()

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('authenticated'),
    )

    // Directly drive the apiClient refresh path that fires onSessionCleared.
    await act(async () => {
      await refreshOnce()
    })

    await waitFor(() =>
      expect(screen.getByTestId('status')).toHaveTextContent('unauthenticated'),
    )
    expect(screen.getByTestId('userId')).toHaveTextContent('∅')
  })
})

describe('useAuth — outside the provider', () => {
  it('throws a clear error', () => {
    // Silence the React error-boundary console noise for the expected throw.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Probe />)).toThrow(/AuthProvider/)
    spy.mockRestore()
  })
})
