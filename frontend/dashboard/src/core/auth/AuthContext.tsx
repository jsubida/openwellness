// Dashboard auth state + lifecycle. No 1:1 mobile mirror — mobile holds session
// state in Koin singletons gated server-side; the web equivalent is this React
// context provider plus a UX-only role gate. The session type lives in core/
// (not features/) because core may NOT import features/ (ESLint-enforced), and
// the revoker is INJECTED for the same reason: core cannot reach
// features/auth/api/revokeToken directly.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { refreshOnce, setOnSessionCleared } from '../api/apiClient'
import { decodeAccessClaims, hasCoachOrAdminRole } from './jwt'
import { tokenStorage } from './tokenStorage'

export interface SessionInfo {
  userId: string
  participant: string | null
  roles: string[]
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

export interface SignInPayload {
  tokens: { accessToken: string; refreshToken: string }
  session: SessionInfo
}

interface AuthContextValue {
  status: AuthStatus
  session: SessionInfo | null
  signIn: (payload: SignInPayload) => void
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Build a SessionInfo from decoded access-token claims. Caller owns role gating.
 */
function sessionFromAccessToken(accessToken: string): SessionInfo | null {
  const claims = decodeAccessClaims(accessToken)
  if (claims == null || !hasCoachOrAdminRole(claims)) return null
  return {
    userId: claims.sub ?? '',
    participant:
      typeof claims.participant === 'string' ? claims.participant : null,
    roles: claims.roles,
  }
}

export function AuthProvider(props: {
  children: ReactNode
  /**
   * Injected revoker (e.g. features/auth/api revokeToken) — core cannot import
   * features. Never throws (returns a Result), but treat defensively anyway.
   */
  revokeSession?: (refreshToken: string) => Promise<unknown>
}) {
  const { children, revokeSession } = props
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [session, setSession] = useState<SessionInfo | null>(null)

  // StrictMode runs mount → cleanup → remount synchronously. We deliberately do
  // NOT guard with a "bootstrapped once" ref: that would let mount #1's in-flight
  // bootstrap bail on its `cancelled` flag while mount #2 early-returns, leaving
  // status stuck on 'loading' forever. Instead we use only the per-effect
  // `cancelled` flag. The remount's bootstrap re-enters refreshOnce() while
  // mount #1's call is still in flight and SHARES it (single-flight → one network
  // call); mount #2's closure (cancelled=false) is the one that applies state.
  useEffect(() => {
    let cancelled = false

    async function bootstrap(): Promise<void> {
      // No stored refresh token → unauthenticated with NO network call.
      if (tokenStorage.getRefreshToken() == null) {
        if (!cancelled) setStatus('unauthenticated')
        return
      }

      const refreshed = await refreshOnce()
      if (cancelled) return

      // refreshOnce already cleared storage on failure; just route the status.
      if (!refreshed.ok) {
        setStatus('unauthenticated')
        return
      }

      const next = sessionFromAccessToken(tokenStorage.getAccessToken() ?? '')
      if (next == null) {
        // Refresh succeeded but the role gate failed (or claims undecodable).
        tokenStorage.clear()
        setStatus('unauthenticated')
        return
      }

      setSession(next)
      setStatus('authenticated')
    }

    void bootstrap()

    return () => {
      cancelled = true
    }
  }, [])

  // Mid-session refresh failure routing. The apiClient has ALREADY cleared
  // tokenStorage when this fires — do NOT call revoke here.
  useEffect(() => {
    setOnSessionCleared(() => {
      setSession(null)
      setStatus('unauthenticated')
    })
    return () => setOnSessionCleared(null)
  }, [])

  const signIn = useCallback((payload: SignInPayload): void => {
    // Caller has already role-gated; the provider does NOT re-gate here.
    tokenStorage.setTokens(payload.tokens)
    setSession(payload.session)
    setStatus('authenticated')
  }, [])

  const signOut = useCallback(async (): Promise<void> => {
    const refreshToken = tokenStorage.getRefreshToken()
    if (refreshToken != null) {
      try {
        // Best-effort revoke; failures are the injected function's business.
        await revokeSession?.(refreshToken)
      } catch {
        // Ignore — we're tearing the session down regardless.
      }
    }
    tokenStorage.clear()
    setSession(null)
    setStatus('unauthenticated')
  }, [revokeSession])

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, signIn, signOut }),
    [status, session, signIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (value == null) {
    throw new Error('useAuth must be used within an <AuthProvider>.')
  }
  return value
}
