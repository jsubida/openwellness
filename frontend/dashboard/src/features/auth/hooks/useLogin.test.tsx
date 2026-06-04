// Tests for features/auth/hooks/useLogin.ts — the React port of the mobile
// LoginViewModel. Mirrors LoginViewModelTest.kt + FakeAuthRepository.kt, with
// new web-only role-gate cases. The API is mocked at the module boundary
// (the web analog of FakeAuthRepository); fake coach/participant JWTs are
// built base64url-style exactly like jwt.test / AuthContext.test.
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, useAuth } from '@/core/auth/AuthContext'
import { tokenStorage } from '@/core/auth/tokenStorage'
import { ok, err } from '@/core/result'
import * as authApi from '@/features/auth/api/authApi'
import { authErrorMessage } from '@/features/auth/model/messages'
import { useLogin } from './useLogin'

// Mock the API at the module boundary — the web FakeAuthRepository analog.
vi.mock('@/features/auth/api/authApi')

const VALID_EMAIL = 'person@example.com'
const VALID_CODE = '123456'

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

const coachJwt = fakeJwt({ sub: 'users/u1', roles: ['coach'] })
const participantJwt = fakeJwt({ sub: 'users/u2', roles: ['participant'] })

function authSession(accessToken: string) {
  return {
    tokens: {
      accessToken,
      refreshToken: 'refresh-token',
      tokenType: 'Bearer',
      expiresInSeconds: 900,
    },
    principal: { userId: 'users/u1', participant: null },
  }
}

// Probe that renders the live hook state and wires each action to a button.
function LoginProbe() {
  const s = useLogin()
  return (
    <div>
      <span data-testid="step">{s.step}</span>
      <span data-testid="email">{s.email}</span>
      <span data-testid="code">{s.code}</span>
      <span data-testid="loading">{String(s.isLoading)}</span>
      <span data-testid="error">{s.error ?? '∅'}</span>
      <span data-testid="emailError">{s.emailError ?? '∅'}</span>
      <span data-testid="codeError">{s.codeError ?? '∅'}</span>
      <span data-testid="resendInSeconds">{s.resendInSeconds}</span>
      <span data-testid="canResend">{String(s.canResend)}</span>
      <button onClick={() => s.onEmailChange(VALID_EMAIL)}>
        set-valid-email
      </button>
      <button onClick={() => s.onEmailChange('not-an-email')}>
        set-invalid-email
      </button>
      <button onClick={() => s.onEmailChange('nobody@nowhere.test')}>
        set-unknown-email
      </button>
      <button onClick={() => s.onCodeChange(VALID_CODE)}>set-valid-code</button>
      <button onClick={() => s.onCodeChange('12a')}>set-invalid-code</button>
      <button onClick={() => s.onSendCodeClick()}>send</button>
      <button onClick={() => s.onVerifyClick()}>verify</button>
      <button onClick={() => s.onResendClick()}>resend</button>
      <button onClick={() => s.onBackToEmail()}>back</button>
      <button onClick={() => s.onErrorDismiss()}>dismiss</button>
    </div>
  )
}

// Home probe: proves navigation happened + reads the authenticated userId.
function HomeProbe() {
  const { session } = useAuth()
  return (
    <div>
      <span data-testid="home">home</span>
      <span data-testid="homeUserId">{session?.userId ?? '∅'}</span>
    </div>
  )
}

// Auth probe that lives at "/" alongside the login probe so authenticated
// status is observable even when navigation does NOT happen (gate-fail cases).
function AuthStatusProbe() {
  const { status } = useAuth()
  return <span data-testid="authStatus">{status}</span>
}

function renderLogin() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    )
  }
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route
            path="/"
            element={
              <>
                <AuthStatusProbe />
                <LoginProbe />
              </>
            }
          />
          <Route path="/home" element={<HomeProbe />} />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  )
}

const send = () =>
  vi.mocked(authApi.sendLoginCode) as unknown as ReturnType<typeof vi.fn>
const verify = () =>
  vi.mocked(authApi.verifyLoginCode) as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  tokenStorage.clear()
  localStorage.clear()
  vi.mocked(authApi.sendLoginCode).mockReset()
  vi.mocked(authApi.verifyLoginCode).mockReset()
  // Default happy-path stubs (FakeAuthRepository defaults: 60s resend, coach).
  vi.mocked(authApi.sendLoginCode).mockResolvedValue(
    ok({ expiresInSeconds: 900, resendAfterSeconds: 60, message: 'ok' }),
  )
  vi.mocked(authApi.verifyLoginCode).mockResolvedValue(
    ok(authSession(coachJwt)),
  )
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useLogin — send', () => {
  it('advances to EnterCode and seeds the cooldown from resendAfterSeconds on a valid send', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))

    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )
    expect(send()).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('60')
    expect(screen.getByTestId('canResend')).toHaveTextContent('false')
  })

  it('advances identically for an unknown email (anti-enumeration)', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-unknown-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))

    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )
  })

  it('blocks send on an invalid email — sets emailError, no network call', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-invalid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))

    expect(screen.getByTestId('emailError')).not.toHaveTextContent('∅')
    expect(screen.getByTestId('step')).toHaveTextContent('EnterEmail')
    expect(send()).not.toHaveBeenCalled()
  })
})

describe('useLogin — cooldown', () => {
  // These tests drive the per-second cooldown interval with fake timers. We use
  // synchronous fireEvent clicks (not async user-event) wrapped in act, and
  // flush the mutation microtask with `await act(async () => {})` — RTL's async
  // waitFor cannot poll while fake timers are installed.
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  // Drive a valid email + send and flush the (mocked) send mutation's promise.
  async function clickSendAndFlush(buttonName = 'send') {
    fireEvent.click(screen.getByRole('button', { name: 'set-valid-email' }))
    fireEvent.click(screen.getByRole('button', { name: buttonName }))
    // Flush the resolved mutateAsync microtask under fake timers.
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('ticks the cooldown down to 0 and flips canResend true', async () => {
    renderLogin()

    await clickSendAndFlush()
    expect(screen.getByTestId('step')).toHaveTextContent('EnterCode')
    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('60')
    expect(screen.getByTestId('canResend')).toHaveTextContent('false')

    await act(async () => {
      vi.advanceTimersByTime(60_000)
    })

    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('0')
    expect(screen.getByTestId('canResend')).toHaveTextContent('true')
  })

  it('ignores resend while the cooldown is active (send called once total)', async () => {
    renderLogin()

    await clickSendAndFlush()
    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('60')
    expect(screen.getByTestId('canResend')).toHaveTextContent('false')

    fireEvent.click(screen.getByRole('button', { name: 'resend' }))
    await act(async () => {
      await Promise.resolve()
    })

    expect(send()).toHaveBeenCalledTimes(1)
  })

  it('allows resend after the cooldown elapses and re-seeds it', async () => {
    renderLogin()

    await clickSendAndFlush()
    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('60')

    await act(async () => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getByTestId('canResend')).toHaveTextContent('true')

    // Second response re-seeds with a fresh value to prove re-seeding works.
    vi.mocked(authApi.sendLoginCode).mockResolvedValue(
      ok({ expiresInSeconds: 900, resendAfterSeconds: 30, message: 'ok' }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'resend' }))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(send()).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('30')
    expect(screen.getByTestId('canResend')).toHaveTextContent('false')
  })
})

describe('useLogin — verify', () => {
  it('blocks verify on an invalid OTP — sets codeError, no network call', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'set-invalid-code' }))
    await user.click(screen.getByRole('button', { name: 'verify' }))

    expect(screen.getByTestId('codeError')).not.toHaveTextContent('∅')
    expect(verify()).not.toHaveBeenCalled()
  })

  it('signs in with a coach JWT, persists tokens, and navigates to /home', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'set-valid-code' }))
    await user.click(screen.getByRole('button', { name: 'verify' }))

    await waitFor(() => expect(screen.getByTestId('home')).toBeInTheDocument())
    expect(screen.getByTestId('homeUserId')).toHaveTextContent('users/u1')
    expect(tokenStorage.getAccessToken()).toBe(coachJwt)
    expect(tokenStorage.getRefreshToken()).toBe('refresh-token')
  })

  it('shows the uniform invalid-or-expired message and stays on EnterCode on a 400', async () => {
    vi.mocked(authApi.verifyLoginCode).mockResolvedValue(
      err({ kind: 'InvalidOrExpiredCode' }),
    )
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'set-valid-code' }))
    await user.click(screen.getByRole('button', { name: 'verify' }))

    await waitFor(() =>
      expect(screen.getByTestId('codeError')).toHaveTextContent(
        authErrorMessage({ kind: 'InvalidOrExpiredCode' }),
      ),
    )
    expect(screen.getByTestId('step')).toHaveTextContent('EnterCode')
    expect(screen.queryByTestId('home')).not.toBeInTheDocument()
  })

  it('on a 429 during verify shows the rate-limited banner and seeds the cooldown', async () => {
    vi.mocked(authApi.verifyLoginCode).mockResolvedValue(
      err({ kind: 'RateLimited', retryAfterSeconds: 42 }),
    )
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'set-valid-code' }))
    await user.click(screen.getByRole('button', { name: 'verify' }))

    await waitFor(() =>
      expect(screen.getByTestId('error')).toHaveTextContent('42'),
    )
    expect(screen.getByTestId('resendInSeconds')).toHaveTextContent('42')
  })

  it('rejects a participant JWT: NotAuthorized banner, no signIn, no navigation, storage stays empty', async () => {
    vi.mocked(authApi.verifyLoginCode).mockResolvedValue(
      ok({
        tokens: {
          accessToken: participantJwt,
          refreshToken: 'refresh-token',
          tokenType: 'Bearer',
          expiresInSeconds: 900,
        },
        principal: { userId: 'users/u2', participant: null },
      }),
    )
    const user = userEvent.setup()
    renderLogin()

    // Wait for bootstrap to settle (no token → unauthenticated, no network).
    await waitFor(() =>
      expect(screen.getByTestId('authStatus')).toHaveTextContent(
        'unauthenticated',
      ),
    )

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'set-valid-code' }))
    await user.click(screen.getByRole('button', { name: 'verify' }))

    await waitFor(() =>
      expect(screen.getByTestId('error')).toHaveTextContent(
        authErrorMessage({ kind: 'NotAuthorized' }),
      ),
    )
    expect(screen.queryByTestId('home')).not.toBeInTheDocument()
    expect(screen.getByTestId('step')).toHaveTextContent('EnterCode')
    expect(screen.getByTestId('authStatus')).toHaveTextContent(
      'unauthenticated',
    )
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })
})

describe('useLogin — in-flight latch (double-click guard)', () => {
  it('two synchronous send clicks before the mutation resolves call send exactly once', async () => {
    // Controllable deferred promise — first call is still in flight for second click.
    let resolve!: (v: ReturnType<typeof ok>) => void
    const deferred = new Promise<ReturnType<typeof ok>>((res) => {
      resolve = res
    })
    vi.mocked(authApi.sendLoginCode).mockReturnValue(deferred as never)

    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))

    // Fire two clicks synchronously before the deferred resolves.
    fireEvent.click(screen.getByRole('button', { name: 'send' }))
    fireEvent.click(screen.getByRole('button', { name: 'send' }))

    // Flush microtasks so TanStack Query dispatches the mutation fn for the
    // first click — the second click is already blocked by inFlightRef.
    await act(async () => {
      await Promise.resolve()
    })

    expect(send()).toHaveBeenCalledTimes(1)

    // Resolve so the component settles cleanly.
    resolve(
      ok({ expiresInSeconds: 900, resendAfterSeconds: 60, message: 'ok' }),
    )
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )
  })

  it('two synchronous verify clicks before the mutation resolves call verify exactly once', async () => {
    // Controllable deferred promise for the verify mutation.
    let resolve!: (v: ReturnType<typeof ok>) => void
    const deferred = new Promise<ReturnType<typeof ok>>((res) => {
      resolve = res
    })
    vi.mocked(authApi.verifyLoginCode).mockReturnValue(deferred as never)

    const user = userEvent.setup()
    renderLogin()

    // Advance to EnterCode using the default (resolved) send stub.
    vi.mocked(authApi.sendLoginCode).mockResolvedValue(
      ok({ expiresInSeconds: 900, resendAfterSeconds: 60, message: 'ok' }),
    )
    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'set-valid-code' }))

    // Fire two verify clicks synchronously before the deferred resolves.
    fireEvent.click(screen.getByRole('button', { name: 'verify' }))
    fireEvent.click(screen.getByRole('button', { name: 'verify' }))

    // Flush microtasks so TanStack Query dispatches the mutation fn for the
    // first click — the second click is already blocked by inFlightRef.
    await act(async () => {
      await Promise.resolve()
    })

    expect(verify()).toHaveBeenCalledTimes(1)

    // Resolve so the component settles cleanly.
    resolve(ok(authSession(coachJwt)))
    await waitFor(() => expect(screen.getByTestId('home')).toBeInTheDocument())
  })
})

describe('useLogin — navigation + dismiss', () => {
  it('onBackToEmail returns to EnterEmail keeping the email value', async () => {
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )

    await user.click(screen.getByRole('button', { name: 'back' }))

    expect(screen.getByTestId('step')).toHaveTextContent('EnterEmail')
    expect(screen.getByTestId('email')).toHaveTextContent(VALID_EMAIL)
  })

  it('onErrorDismiss clears the banner error', async () => {
    vi.mocked(authApi.verifyLoginCode).mockResolvedValue(
      err({ kind: 'RateLimited', retryAfterSeconds: 42 }),
    )
    const user = userEvent.setup()
    renderLogin()

    await user.click(screen.getByRole('button', { name: 'set-valid-email' }))
    await user.click(screen.getByRole('button', { name: 'send' }))
    await waitFor(() =>
      expect(screen.getByTestId('step')).toHaveTextContent('EnterCode'),
    )
    await user.click(screen.getByRole('button', { name: 'set-valid-code' }))
    await user.click(screen.getByRole('button', { name: 'verify' }))
    await waitFor(() =>
      expect(screen.getByTestId('error')).not.toHaveTextContent('∅'),
    )

    await user.click(screen.getByRole('button', { name: 'dismiss' }))

    expect(screen.getByTestId('error')).toHaveTextContent('∅')
  })
})
