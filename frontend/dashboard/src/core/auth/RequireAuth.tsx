// Route-guard layout route for react-router v7. No 1:1 mobile mirror — mobile
// gates navigation server-side; this is the dashboard's client-side guard,
// rendered as a layout route wrapping the protected subtree via <Outlet />.
import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from './AuthContext'
import { decodeAccessClaims, hasCoachOrAdminRole } from './jwt'
import { tokenStorage } from './tokenStorage'

export function RequireAuth() {
  const { status } = useAuth()

  if (status === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div
          role="status"
          aria-label="Loading"
          className="size-8 animate-spin rounded-full border-2 border-muted border-t-primary"
        />
      </div>
    )
  }

  // Redirect to "/", which MUST stay a public (login) route — if it were itself
  // guarded, an unauthenticated user would redirect into a loop. We intentionally
  // do NOT clear tokens here: bootstrap and the apiClient's onSessionCleared
  // callback own teardown; the guard only routes.
  if (status === 'unauthenticated') {
    return <Navigate to="/" replace />
  }

  // Defense-in-depth: re-check the live access token's role at render time, not
  // just the cached status (the access token can rotate between renders). Same
  // redirect contract as above: "/" stays public, and we do not clear tokens.
  const claims = decodeAccessClaims(tokenStorage.getAccessToken() ?? '')
  if (!hasCoachOrAdminRole(claims)) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
