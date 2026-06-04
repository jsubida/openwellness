// Mirrors LoginScreen.kt EmailStep (feature/auth/presentation/.../login/).
// The web FUSES Landing + Login into one screen, so this is the first thing the
// user sees. Pure + props-driven: it owns no state and reads no context — the
// LandingLoginPage host passes the exact useLogin slices it needs.
import { EmailField } from '@/core/ui/EmailField'
import { LoadingButton } from '@/core/ui/LoadingButton'

import { ErrorBanner } from './ErrorBanner'

export interface EmailStepProps {
  email: string
  emailError: string | null
  /** Banner-level (already-mapped) error string, or null when none. */
  error: string | null
  isLoading: boolean
  onEmailChange: (value: string) => void
  onSendCodeClick: () => void
  onErrorDismiss: () => void
}

export function EmailStep({
  email,
  emailError,
  error,
  isLoading,
  onEmailChange,
  onSendCodeClick,
  onErrorDismiss,
}: EmailStepProps) {
  function handleSubmit(e: React.FormEvent) {
    // A real form so Enter submits natively. We do NOT also wire EmailField's
    // `onEnter` (its JSDoc warns about the double-fire footgun).
    e.preventDefault()
    onSendCodeClick()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <EmailField
        value={email}
        onChange={onEmailChange}
        error={emailError}
        disabled={isLoading}
        autoFocus
      />

      {error && <ErrorBanner message={error} onDismiss={onErrorDismiss} />}

      <LoadingButton type="submit" loading={isLoading}>
        Send code
      </LoadingButton>
    </form>
  )
}
