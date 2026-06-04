// End-to-end integration suite: drives the REAL <App/> through the network
// boundary with MSW. UI → useLogin → TanStack mutations → authApi → apiClient
// fetch → MSW. The web analog of the mobile Ktor MockEngine login suites.
//
// MSW lifecycle is scoped to THIS file (beforeAll listen / afterEach reset /
// afterAll close) so the 135 existing fetch-stubbing suites stay untouched.
// Real timers throughout — fake timers + MSW's async request resolution race;
// findBy/waitFor poll the DOM until the network round-trips settle.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from 'vitest'

import { tokenStorage } from '@/core/auth/tokenStorage'
import { authErrorMessage } from '@/features/auth/model/messages'

import App from '@/app/App'
import {
  aipError,
  apiUrl,
  participantToken,
  tokenResponseBody,
} from '@/test/msw/handlers'
import { server } from '@/test/msw/server'

const COACH_EMAIL = 'coach@example.com'
const REFRESH_KEY = 'openwellness.refreshToken'
const PARTICIPANT_PRINCIPAL = {
  userId: 'users/u2',
  participant: 'participants/p2',
}

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

beforeEach(() => {
  tokenStorage.clear()
  localStorage.clear()
  window.history.pushState({}, '', '/')
})

describe('login flow — end to end through MSW', () => {
  it('signs a coach all the way in, persists tokens, and revokes on sign out', async () => {
    // Capture the refresh token the revoke endpoint actually receives.
    let revokedRefreshToken: string | null = null
    server.use(
      http.post(apiUrl('auth:revokeToken'), async ({ request }) => {
        const body = (await request.json()) as { refreshToken?: string }
        revokedRefreshToken = body.refreshToken ?? null
        return HttpResponse.json({ status: 'revoked' })
      }),
    )

    const user = userEvent.setup()
    render(<App />)

    // Landing: the login form is the landing page.
    expect(
      await screen.findByRole('heading', { name: 'OpenWellness' }),
    ).toBeInTheDocument()

    // Enter email + send the code.
    await user.type(screen.getByLabelText('Email'), COACH_EMAIL)
    await user.click(screen.getByRole('button', { name: 'Send code' }))

    // CodeStep appears with the "code sent" copy naming the email.
    expect(
      await screen.findByText(/Enter the 6-digit code/i),
    ).toBeInTheDocument()
    expect(screen.getByText(COACH_EMAIL)).toBeInTheDocument()

    // Type the 6-digit code — OtpInput auto-submits on the 6th digit (onFilled),
    // so we do NOT click Verify.
    await user.type(screen.getByLabelText('6-digit code'), '123456')

    // Lands on /home, signed in as the coach userId. "Signed in as" is a
    // CardTitle <div> (not a heading), so query it by text + the userId text.
    expect(await screen.findByText('Signed in as')).toBeInTheDocument()
    expect(screen.getByText('users/u1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()

    // Tokens persisted: access in memory, refresh in localStorage.
    expect(tokenStorage.getAccessToken()).not.toBeNull()
    expect(tokenStorage.getRefreshToken()).toBe('refresh-1')
    expect(localStorage.getItem(REFRESH_KEY)).toBe('refresh-1')

    // Sign out → revoke fires with the stored refresh token, storage clears,
    // and we land back on the landing email form.
    await user.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    await waitFor(() => expect(tokenStorage.getRefreshToken()).toBeNull())
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(revokedRefreshToken).toBe('refresh-1')
  })

  it('rejects a participant token: NotAuthorized banner, stays on code step, storage empty', async () => {
    server.use(
      http.post(apiUrl('auth:verifyLoginCode'), () =>
        HttpResponse.json(
          tokenResponseBody(
            participantToken,
            'refresh-2',
            PARTICIPANT_PRINCIPAL,
          ),
        ),
      ),
    )

    const user = userEvent.setup()
    render(<App />)

    await screen.findByRole('heading', { name: 'OpenWellness' })
    await user.type(screen.getByLabelText('Email'), COACH_EMAIL)
    await user.click(screen.getByRole('button', { name: 'Send code' }))

    await screen.findByText(/Enter the 6-digit code/i)
    await user.type(screen.getByLabelText('6-digit code'), '123456')

    // NotAuthorized banner appears (exact message from messages.ts).
    expect(
      await screen.findByText(authErrorMessage({ kind: 'NotAuthorized' })),
    ).toBeInTheDocument()

    // Still on the code step; never signed in; storage stays empty.
    expect(screen.getByLabelText('6-digit code')).toBeInTheDocument()
    expect(screen.queryByText('Signed in as')).not.toBeInTheDocument()
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it('shows the uniform invalid-or-expired message on a 400 and stays on the code step', async () => {
    server.use(
      http.post(apiUrl('auth:verifyLoginCode'), () =>
        aipError(400, 'INVALID_ARGUMENT', 'Invalid or expired code.'),
      ),
    )

    const user = userEvent.setup()
    render(<App />)

    await screen.findByRole('heading', { name: 'OpenWellness' })
    await user.type(screen.getByLabelText('Email'), COACH_EMAIL)
    await user.click(screen.getByRole('button', { name: 'Send code' }))

    await screen.findByText(/Enter the 6-digit code/i)
    await user.type(screen.getByLabelText('6-digit code'), '123456')

    // The codeError inline text is the uniform invalid-or-expired wording.
    expect(
      await screen.findByText(
        authErrorMessage({ kind: 'InvalidOrExpiredCode' }),
      ),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('6-digit code')).toBeInTheDocument()
    expect(screen.queryByText('Signed in as')).not.toBeInTheDocument()
  })

  it('bootstraps a stored coach session straight into /home with no login interaction', async () => {
    // A stored refresh token + landing on /home → bootstrap refreshes and the
    // (default) refresh handler returns a coach pair.
    localStorage.setItem(REFRESH_KEY, 'stored-refresh')
    window.history.pushState({}, '', '/home')

    render(<App />)

    expect(await screen.findByText('Signed in as')).toBeInTheDocument()
    expect(screen.getByText('users/u1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
    // No login form was ever shown.
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
  })

  it('bootstrap role-gate negative: a participant refresh redirects to the landing form, storage cleared', async () => {
    localStorage.setItem(REFRESH_KEY, 'stored-refresh')
    window.history.pushState({}, '', '/home')

    server.use(
      http.post(apiUrl('auth:refreshToken'), () =>
        HttpResponse.json(
          tokenResponseBody(
            participantToken,
            'rotated-refresh',
            PARTICIPANT_PRINCIPAL,
          ),
        ),
      ),
    )

    render(<App />)

    // Redirected to the landing email form; never reaches Home.
    expect(await screen.findByLabelText('Email')).toBeInTheDocument()
    expect(screen.queryByText('Signed in as')).not.toBeInTheDocument()
    // Bootstrap clears storage when the role gate fails.
    await waitFor(() => expect(tokenStorage.getRefreshToken()).toBeNull())
    expect(tokenStorage.getAccessToken()).toBeNull()
  })
})
