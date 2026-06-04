// Mirrors LoginViewModel.kt + LoginContract.kt
// (feature/auth/presentation/src/commonMain/.../login/). React port of the
// mobile login step machine: send ALWAYS advances to EnterCode on success
// (anti-enumeration), a 429 seeds the authoritative resend cooldown, and the
// resend cooldown ticks down once per second.
//
// Divergences from the Kotlin VM (web-only reasons, see plan):
//   - Role gate on verify success. Mobile gates server-side and simply emits
//     NavigateToHome; the dashboard must additionally decode the access token
//     and reject non-coach/admin accounts (NotAuthorized) BEFORE signing in.
//   - onCodeChange clears codeError ONLY (per the web hook spec). The Kotlin
//     OnCodeChange additionally clears the banner error; we follow the spec.
//   - No SavedStateHandle persistence — there is no process death on the web;
//     a reload restarts the flow, which is acceptable for a login screen.
//   - Server-error routing moved from banner-only (mobile VM puts every
//     AuthError in the single banner slot) to per-field on web: InvalidEmail
//     → emailError, InvalidCode/InvalidOrExpiredCode → codeError.

import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '@/core/auth/AuthContext'
import { decodeAccessClaims, hasCoachOrAdminRole } from '@/core/auth/jwt'
import { tokenStorage } from '@/core/auth/tokenStorage'
import type { AuthError } from '@/features/auth/model/errors'
import { authErrorMessage } from '@/features/auth/model/messages'
import {
  validateEmail,
  validateOtpCode,
} from '@/features/auth/model/validators'
import {
  useSendLoginCode,
  useVerifyLoginCode,
} from '@/features/auth/api/mutations'

export type LoginStep = 'EnterEmail' | 'EnterCode'

export interface LoginState {
  step: LoginStep
  email: string
  code: string
  isLoading: boolean
  /** Banner-level message — already mapped via authErrorMessage. */
  error: string | null
  emailError: string | null
  codeError: string | null
  resendInSeconds: number
  canResend: boolean
}

export interface LoginActions {
  onEmailChange(v: string): void
  onCodeChange(v: string): void
  onSendCodeClick(): void
  onVerifyClick(): void
  onResendClick(): void
  onBackToEmail(): void
  onErrorDismiss(): void
}

const INITIAL_STATE: LoginState = {
  step: 'EnterEmail',
  email: '',
  code: '',
  isLoading: false,
  error: null,
  emailError: null,
  codeError: null,
  resendInSeconds: 0,
  canResend: false,
}

type Action =
  | { type: 'emailChange'; email: string }
  | { type: 'codeChange'; code: string }
  // `clearField` matches the VM: send-start clears emailError, verify-start
  // clears codeError; both clear the banner error.
  | { type: 'loadingStart'; clearField: 'email' | 'code' }
  | { type: 'loadingStop' }
  | { type: 'sendSuccess' }
  | { type: 'emailError'; message: string }
  | { type: 'codeError'; message: string }
  | { type: 'bannerError'; message: string }
  | { type: 'backToEmail' }
  | { type: 'dismissError' }
  // Cooldown is driven by setInterval; the reducer only holds the remaining
  // seconds. `seedCooldown(0)` clears it (canResend = true, 0 remaining).
  | { type: 'seedCooldown'; seconds: number }
  | { type: 'tick' }

function reducer(state: LoginState, action: Action): LoginState {
  switch (action.type) {
    case 'emailChange':
      // Mirrors OnEmailChange: update email, clear the field error.
      return { ...state, email: action.email, emailError: null }
    case 'codeChange':
      // Web spec: clear codeError ONLY (the Kotlin VM also clears the banner).
      return { ...state, code: action.code, codeError: null }
    case 'loadingStart':
      return {
        ...state,
        isLoading: true,
        error: null,
        emailError: action.clearField === 'email' ? null : state.emailError,
        codeError: action.clearField === 'code' ? null : state.codeError,
      }
    case 'loadingStop':
      return { ...state, isLoading: false }
    case 'sendSuccess':
      // ALWAYS advance to EnterCode (anti-enumeration), clearing code state.
      return {
        ...state,
        isLoading: false,
        step: 'EnterCode',
        code: '',
        codeError: null,
        error: null,
      }
    case 'emailError':
      return { ...state, emailError: action.message }
    case 'codeError':
      return { ...state, codeError: action.message }
    case 'bannerError':
      return { ...state, error: action.message }
    case 'backToEmail':
      // Return to EnterEmail; clear code/codeError/banner; KEEP email and the
      // running cooldown (mirrors OnBackToEmail — does not touch resend state).
      return {
        ...state,
        step: 'EnterEmail',
        code: '',
        codeError: null,
        error: null,
      }
    case 'dismissError':
      return { ...state, error: null }
    case 'seedCooldown': {
      const seconds = Math.max(0, action.seconds)
      return {
        ...state,
        resendInSeconds: seconds,
        canResend: seconds === 0,
      }
    }
    case 'tick': {
      const next = Math.max(0, state.resendInSeconds - 1)
      return { ...state, resendInSeconds: next, canResend: next === 0 }
    }
    default:
      return state
  }
}

export function useLogin(): LoginState & LoginActions {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  const { signIn } = useAuth()
  const navigate = useNavigate()
  const sendMutation = useSendLoginCode()
  const verifyMutation = useVerifyLoginCode()

  // setInterval handle for the active cooldown — survives re-renders.
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Guards against dispatching after unmount once an awaited mutation resolves.
  const aliveRef = useRef(true)
  // Synchronous in-flight latch: prevents two rapid clicks both passing through
  // before React commits the isLoading=true state update from loadingStart.
  const inFlightRef = useRef(false)
  // TanStack Query v5 binds mutateAsync once per observer (component lifetime),
  // so its identity is stable across renders — safe to depend on directly.
  const sendAsync = sendMutation.mutateAsync
  const verifyAsync = verifyMutation.mutateAsync

  const clearCooldown = useCallback(() => {
    if (intervalRef.current != null) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  // Seed the cooldown to `seconds` and tick down 1/s to 0. Re-seeding clears
  // the previous interval first (mirrors cooldownJob?.cancel()).
  const startCooldown = useCallback(
    (seconds: number) => {
      clearCooldown()
      dispatch({ type: 'seedCooldown', seconds })
      if (seconds <= 0) return
      intervalRef.current = setInterval(() => {
        if (!aliveRef.current) {
          clearCooldown()
          return
        }
        dispatch({ type: 'tick' })
      }, 1000)
    },
    [clearCooldown],
  )

  // Unmount cleanup: stop the interval and block any pending awaited dispatch.
  useEffect(() => {
    aliveRef.current = true
    return () => {
      aliveRef.current = false
      clearCooldown()
    }
  }, [clearCooldown])

  // Stop ticking once we reach zero (canResend latched true). Re-seeding starts
  // a fresh interval, so this only fires on the natural countdown completion.
  useEffect(() => {
    if (state.resendInSeconds === 0) clearCooldown()
  }, [state.resendInSeconds, clearCooldown])

  // Route an AuthError to the right slot (mirrors handleAuthError + the VM's
  // per-field error placement). A 429 ALSO seeds the authoritative cooldown.
  const routeError = useCallback(
    (error: AuthError) => {
      const message = authErrorMessage(error)
      switch (error.kind) {
        case 'InvalidEmail':
          dispatch({ type: 'emailError', message })
          return
        case 'InvalidCode':
        case 'InvalidOrExpiredCode':
          dispatch({ type: 'codeError', message })
          return
        case 'RateLimited':
          startCooldown(error.retryAfterSeconds)
          dispatch({ type: 'bannerError', message })
          return
        default:
          dispatch({ type: 'bannerError', message })
      }
    },
    [startCooldown],
  )

  const doSend = useCallback(
    async (isResend: boolean) => {
      if (inFlightRef.current) return
      if (isResend && !state.canResend) return

      const email = state.email.trim()
      if (!validateEmail(email).ok) {
        dispatch({
          type: 'emailError',
          message: authErrorMessage({ kind: 'InvalidEmail' }),
        })
        return
      }

      inFlightRef.current = true
      dispatch({ type: 'loadingStart', clearField: 'email' })
      try {
        const result = await sendAsync(email)
        if (!aliveRef.current) return
        if (result.ok) {
          dispatch({ type: 'sendSuccess' })
          startCooldown(result.value.resendAfterSeconds)
        } else {
          dispatch({ type: 'loadingStop' })
          routeError(result.error)
        }
      } finally {
        inFlightRef.current = false
      }
    },
    [state.canResend, state.email, sendAsync, startCooldown, routeError],
  )

  const onEmailChange = useCallback((v: string) => {
    dispatch({ type: 'emailChange', email: v })
  }, [])

  const onCodeChange = useCallback((v: string) => {
    dispatch({ type: 'codeChange', code: v })
  }, [])

  const onSendCodeClick = useCallback(() => {
    void doSend(false)
  }, [doSend])

  const onResendClick = useCallback(() => {
    void doSend(true)
  }, [doSend])

  const onVerifyClick = useCallback(() => {
    if (inFlightRef.current) return

    const code = state.code
    if (!validateOtpCode(code).ok) {
      dispatch({
        type: 'codeError',
        message: authErrorMessage({ kind: 'InvalidCode' }),
      })
      return
    }

    inFlightRef.current = true
    void (async () => {
      dispatch({ type: 'loadingStart', clearField: 'code' })
      try {
        const result = await verifyAsync({ email: state.email.trim(), code })
        if (!aliveRef.current) return
        if (!result.ok) {
          dispatch({ type: 'loadingStop' })
          routeError(result.error)
          return
        }

        // Role gate — web-only. Decode the access token and reject non-coach/
        // admin accounts WITHOUT signing in. Defensively clear any token state.
        const session = result.value
        const accessToken = session.tokens.accessToken
        const claims = decodeAccessClaims(accessToken)
        if (!hasCoachOrAdminRole(claims)) {
          tokenStorage.clear()
          dispatch({ type: 'loadingStop' })
          dispatch({
            type: 'bannerError',
            message: authErrorMessage({ kind: 'NotAuthorized' }),
          })
          return
        }

        dispatch({ type: 'loadingStop' })
        signIn({
          tokens: {
            accessToken,
            refreshToken: session.tokens.refreshToken,
          },
          session: {
            userId: session.principal.userId,
            participant: session.principal.participant,
            roles: claims?.roles ?? [],
          },
        })
        navigate('/home', { replace: true })
      } finally {
        inFlightRef.current = false
      }
    })()
  }, [state.code, state.email, verifyAsync, routeError, signIn, navigate])

  const onBackToEmail = useCallback(() => {
    dispatch({ type: 'backToEmail' })
  }, [])

  const onErrorDismiss = useCallback(() => {
    dispatch({ type: 'dismissError' })
  }, [])

  return {
    ...state,
    onEmailChange,
    onCodeChange,
    onSendCodeClick,
    onVerifyClick,
    onResendClick,
    onBackToEmail,
    onErrorDismiss,
  }
}
