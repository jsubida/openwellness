// Mirrors AuthErrorToUiText.kt (feature/auth/presentation/util/AuthErrorToUiText.kt)
// String wording sourced from strings.xml; NotAuthorized is web-only.

import type { AuthError } from './errors'

/**
 * Maps an AuthError to a human-readable UI string.
 *
 * The exhaustive never-check ensures TypeScript errors at compile time if a
 * new AuthError variant is added without a corresponding message.
 */
export function authErrorMessage(error: AuthError): string {
  switch (error.kind) {
    case 'InvalidOrExpiredCode':
      return 'That code is invalid or has expired.'
    case 'RateLimited':
      return `Too many attempts. Please wait ${error.retryAfterSeconds}s and try again.`
    case 'Unauthorized':
      return 'Your session has expired. Please sign in again.'
    case 'NotAuthorized':
      return "This account isn't authorized for the coaching dashboard."
    case 'NoInternet':
      return 'No internet connection. Check your network and try again.'
    case 'Server':
      return "We're having trouble reaching the server. Please try again later."
    case 'Unknown':
      return 'Something went wrong. Please try again.'
    case 'InvalidEmail':
      return 'Enter a valid email address.'
    case 'InvalidCode':
      return 'Enter the 6-digit code.'
    default: {
      // Exhaustiveness check — TS will error here if a variant is unhandled.
      const _exhaustive: never = error
      return _exhaustive
    }
  }
}
