// App-wide providers: TanStack Query + the auth context. app/ is the only
// composition layer permitted to wire features into core (ESLint restricts
// core/, not app/), so the injected revoker lives here.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'

import { AuthProvider } from '@/core/auth/AuthContext'
import { revokeToken } from '@/features/auth/api/authApi'

export function Providers({ children }: { children: ReactNode }) {
  // useState lazy-initialiser: one QueryClient per app instance rather than a
  // module-level singleton — keeps integration tests fully isolated from each
  // other (each render gets a fresh cache). TanStack Query v5 defaults
  // mutations to retry: false and queries to retry: 3; the auth surface is
  // mutation-only here, so the defaults are exactly what we want.
  const [queryClient] = useState(() => new QueryClient())

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider revokeSession={revokeToken}>{children}</AuthProvider>
    </QueryClientProvider>
  )
}
