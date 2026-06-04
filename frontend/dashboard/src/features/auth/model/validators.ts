// Mirrors ValidateEmail.kt + ValidateOtpCode.kt (feature/auth/domain/usecase/)

import type { EmptyResult } from '@/core/result'
import { err, okVoid } from '@/core/result'

import type { AuthError } from './errors'

/**
 * Client-side email shape check (the server is authoritative). Trims first so
 * a trailing space from autofill doesn't fail an otherwise-valid address.
 *
 * Mirrors ValidateEmail.kt regex: ^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$
 * (Kotlin source writes `\-` inside the character class, which is equivalent to `-` at class end.)
 */
export const EMAIL_REGEX = /^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/

export function validateEmail(raw: string): EmptyResult<AuthError> {
  const trimmed = raw.trim()
  if (trimmed.length > 0 && EMAIL_REGEX.test(trimmed)) {
    return okVoid()
  }
  return err<AuthError>({ kind: 'InvalidEmail' })
}

/**
 * The OTP must be exactly six digits, matching the backend's ^\d{6}$ rule.
 *
 * Mirrors ValidateOtpCode.kt — no trim (a space means the code is wrong).
 */
export const OTP_REGEX = /^\d{6}$/

export function validateOtpCode(raw: string): EmptyResult<AuthError> {
  if (OTP_REGEX.test(raw)) {
    return okVoid()
  }
  return err<AuthError>({ kind: 'InvalidCode' })
}
