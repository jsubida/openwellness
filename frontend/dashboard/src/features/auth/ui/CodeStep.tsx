// Mirrors LoginScreen.kt CodeStep (feature/auth/presentation/.../login/).
// Pure + props-driven; no state, no context. OtpInput.onFilled auto-submits
// (same as the mobile onFilled), and the wrapping <form> lets Enter / the
// Verify button submit natively.
import { useId } from 'react'

import { ErrorText } from '@/core/ui/ErrorText'
import { LoadingButton } from '@/core/ui/LoadingButton'
import { OtpInput } from '@/core/ui/OtpInput'
import { Button } from '@/core/ui/button'

import { ErrorBanner } from './ErrorBanner'

export interface CodeStepProps {
  email: string
  code: string
  codeError: string | null
  /** Banner-level (already-mapped) error string, or null when none. */
  error: string | null
  isLoading: boolean
  resendInSeconds: number
  canResend: boolean
  onCodeChange: (value: string) => void
  onVerifyClick: () => void
  onResendClick: () => void
  onBackToEmail: () => void
  onErrorDismiss: () => void
}

export function CodeStep({
  email,
  code,
  codeError,
  error,
  isLoading,
  resendInSeconds,
  canResend,
  onCodeChange,
  onVerifyClick,
  onResendClick,
  onBackToEmail,
  onErrorDismiss,
}: CodeStepProps) {
  const codeErrorId = useId()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    onVerifyClick()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Mirrors auth_code_sent: "Enter the 6-digit code we sent to {email}."
          The mobile string is one line; the web breaks the email onto its own
          line and styles it font-medium for emphasis. */}
      <p className="text-sm text-on-surface-variant">
        Enter the 6-digit code we sent to
        <br />
        <span className="font-medium text-on-surface">{email}</span>
      </p>

      <div className="space-y-2">
        <OtpInput
          value={code}
          onChange={onCodeChange}
          onFilled={() => onVerifyClick()}
          error={Boolean(codeError)}
          disabled={isLoading}
          autoFocus
          aria-describedby={codeError ? codeErrorId : undefined}
        />
        {codeError && <ErrorText id={codeErrorId}>{codeError}</ErrorText>}
      </div>

      {error && <ErrorBanner message={error} onDismiss={onErrorDismiss} />}

      <LoadingButton type="submit" loading={isLoading}>
        Verify
      </LoadingButton>

      {/* Quiet footer row: resend (with cooldown) + change email. Mirrors the
          two TextButtons in LoginScreen.kt's CodeStep. */}
      <div className="flex items-center justify-center gap-3">
        <Button
          type="button"
          variant="ghost"
          disabled={!canResend || isLoading}
          onClick={onResendClick}
        >
          {canResend ? 'Resend code' : `Resend code in ${resendInSeconds}s`}
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={isLoading}
          onClick={onBackToEmail}
        >
          Change email
        </Button>
      </div>
    </form>
  )
}
