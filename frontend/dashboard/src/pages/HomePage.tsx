// Minimal authenticated landing placeholder. Only auth is in scope for this
// task, so this stays small: who you're signed in as + a sign-out action. The
// real coaching dashboard arrives in later tasks.
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/core/auth/AuthContext'
import { Button } from '@/core/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/core/ui/card'

import { ROUTES } from '@/app/routes'

export function HomePage() {
  const { session, signOut } = useAuth()
  const navigate = useNavigate()
  // useRef latch prevents a second click from firing signOut while the first is
  // in flight. useState drives the disabled prop so the button is visually
  // inert; no reset needed — we navigate away on success.
  const signingOutRef = useRef(false)
  const [signingOut, setSigningOut] = useState(false)

  async function handleSignOut() {
    if (signingOutRef.current) return
    signingOutRef.current = true
    setSigningOut(true)
    await signOut()
    navigate(ROUTES.landing)
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Signed in as</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <p className="text-sm break-all text-on-surface-variant">
            {session?.userId ?? '—'}
          </p>
          <Button
            variant="outline"
            className="w-full"
            disabled={signingOut}
            onClick={() => void handleSignOut()}
          >
            Sign out
          </Button>
        </CardContent>
      </Card>
    </main>
  )
}
