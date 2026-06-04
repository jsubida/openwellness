// The web FUSES the mobile LandingScreen + LoginScreen: there is no
// intermediate "Log in" tap — the landing page IS the login form. Hero wordmark
// + subtitle mirror LandingScreen.kt; the step host below mirrors the
// LoginScreen.kt EnterEmail/EnterCode split. This component owns the context
// reads (useAuth, useLogin); the EmailStep/CodeStep children stay pure.
import { Navigate } from 'react-router-dom'

import { useAuth } from '@/core/auth/AuthContext'
import { useLogin } from '@/features/auth/hooks/useLogin'

import { ROUTES } from '@/app/routes'
import { CodeStep } from './CodeStep'
import { EmailStep } from './EmailStep'

export function LandingLoginPage() {
  const { status } = useAuth()
  const login = useLogin()

  // Same minimal spinner pattern as RequireAuth (role="status") while the auth
  // bootstrap resolves, so we never flash the login form to a returning user.
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

  // Already signed in → skip login entirely.
  if (status === 'authenticated') {
    return <Navigate to={ROUTES.home} replace />
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm space-y-8 motion-safe:animate-fade-in-up">
        <header className="space-y-2 text-center">
          <h1 className="text-5xl font-semibold tracking-tight text-primary">
            OpenWellness
          </h1>
          <p className="text-on-surface-variant">
            Your wellness journey starts here.
          </p>
        </header>

        {login.step === 'EnterEmail' ? (
          <EmailStep
            email={login.email}
            emailError={login.emailError}
            error={login.error}
            isLoading={login.isLoading}
            onEmailChange={login.onEmailChange}
            onSendCodeClick={login.onSendCodeClick}
            onErrorDismiss={login.onErrorDismiss}
          />
        ) : (
          <CodeStep
            email={login.email}
            code={login.code}
            codeError={login.codeError}
            error={login.error}
            isLoading={login.isLoading}
            resendInSeconds={login.resendInSeconds}
            canResend={login.canResend}
            onCodeChange={login.onCodeChange}
            onVerifyClick={login.onVerifyClick}
            onResendClick={login.onResendClick}
            onBackToEmail={login.onBackToEmail}
            onErrorDismiss={login.onErrorDismiss}
          />
        )}
      </div>
    </main>
  )
}
