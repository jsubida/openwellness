// TanStack Query v5 mutation hooks for the auth API surface.
// Only file in api/ permitted to import React / @tanstack/react-query.

import { useMutation } from '@tanstack/react-query'
import { sendLoginCode, verifyLoginCode } from './authApi'

/**
 * Wraps sendLoginCode.
 *
 * `mutation.data` / `mutateAsync`'s resolution is always a
 * `Result<SendCodeResult, AuthError>`. Branch on `.ok` — it is never a thrown
 * HTTP error. On success `.ok` is `true` and `.value` carries the send result;
 * on failure `.ok` is `false` and `.error` is the typed `AuthError`.
 */
export function useSendLoginCode() {
  return useMutation({
    mutationFn: (email: string) => sendLoginCode(email),
  })
}

/**
 * Wraps verifyLoginCode.
 *
 * `mutation.data` / `mutateAsync`'s resolution is always a
 * `Result<AuthSession, AuthError>`. Branch on `.ok` — it is never a thrown
 * HTTP error. On success `.ok` is `true` and `.value` is the established
 * `AuthSession`; on failure `.ok` is `false` and `.error` is the typed
 * `AuthError`.
 */
export function useVerifyLoginCode() {
  return useMutation({
    mutationFn: ({ email, code }: { email: string; code: string }) =>
      verifyLoginCode(email, code),
  })
}
