// Mirrors mobile OpenWellnessAuthRepository.kt + AuthRemoteError.kt
// (feature/auth/data/src/commonMain/.../OpenWellnessAuthRepository.kt)

import { refreshOnce, request } from '@/core/api/apiClient'
import type { DataError } from '@/core/errors'
import type { EmptyResult, Result } from '@/core/result'
import { err, map, mapErr, okVoid } from '@/core/result'
import type { AuthError } from '../model/errors'
import type { AuthSession, SendCodeResult } from '../model/types'
import type {
  RevokeResponseDto,
  RevokeTokenRequestDto,
  SendLoginCodeRequestDto,
  TokenResponseDto,
  UniformSendResponseDto,
  VerifyLoginCodeRequestDto,
} from './dtos'
import { toAuthSession, toSendCodeResult } from './mappers'

// --------------------------------------------------------------------------- //
// DataError → AuthError mapping
// Authoritative source: AuthRemoteError.kt `toAuthError()` extension function
//
// BAD_REQUEST        → InvalidOrExpiredCode
// TOO_MANY_REQUESTS  → RateLimited(retryAfterSeconds ?? 60)
// UNAUTHORIZED       → Unauthorized
// NO_INTERNET        → NoInternet
// SERVER_ERROR       → Server
// SERVICE_UNAVAILABLE→ Server
// else               → Unknown
// --------------------------------------------------------------------------- //
export function dataErrorToAuthError(e: DataError): AuthError {
  switch (e.kind) {
    case 'BAD_REQUEST':
      return { kind: 'InvalidOrExpiredCode' }
    case 'TOO_MANY_REQUESTS':
      return {
        kind: 'RateLimited',
        retryAfterSeconds: e.retryAfterSeconds ?? 60,
      }
    case 'UNAUTHORIZED':
      return { kind: 'Unauthorized' }
    case 'NO_INTERNET':
      return { kind: 'NoInternet' }
    case 'SERVER_ERROR':
    case 'SERVICE_UNAVAILABLE':
      return { kind: 'Server' }
    default:
      return { kind: 'Unknown' }
  }
}

export async function sendLoginCode(
  email: string,
): Promise<Result<SendCodeResult, AuthError>> {
  const body: SendLoginCodeRequestDto = { email }
  const result = await request<UniformSendResponseDto>('auth:sendLoginCode', {
    method: 'POST',
    body,
  })
  return mapErr(map(result, toSendCodeResult), dataErrorToAuthError)
}

export async function verifyLoginCode(
  email: string,
  code: string,
): Promise<Result<AuthSession, AuthError>> {
  const body: VerifyLoginCodeRequestDto = { email, code }
  const result = await request<TokenResponseDto>('auth:verifyLoginCode', {
    method: 'POST',
    body,
  })
  return mapErr(map(result, toAuthSession), dataErrorToAuthError)
}

/**
 * Delegates entirely to the core single-flight `refreshOnce()`. Does NOT
 * re-implement token rotation — that lives in apiClient.ts. Maps the
 * transport-level DataError onto AuthError.
 */
export async function refreshSession(): Promise<EmptyResult<AuthError>> {
  const result = await refreshOnce()
  if (result.ok) return okVoid()
  return err(dataErrorToAuthError(result.error))
}

/**
 * Revokes a single refresh token. Requires a valid Bearer access token
 * (auth: true). Mirrors `revokeCurrent` in OpenWellnessAuthRepository.kt.
 */
export async function revokeToken(
  refreshToken: string,
): Promise<EmptyResult<AuthError>> {
  const body: RevokeTokenRequestDto = { refreshToken }
  const result = await request<RevokeResponseDto>('auth:revokeToken', {
    method: 'POST',
    body,
    auth: true,
  })
  if (result.ok) return okVoid()
  return err(dataErrorToAuthError(result.error))
}
