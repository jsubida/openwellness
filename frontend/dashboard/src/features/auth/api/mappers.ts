// Mirrors mobile AuthMappers.kt (feature/auth/data/src/commonMain/.../mapper/AuthMappers.kt)

import type {
  PrincipalDto,
  TokenResponseDto,
  UniformSendResponseDto,
} from './dtos'
import type {
  AuthSession,
  AuthTokens,
  Principal,
  SendCodeResult,
} from '../model/types'

export function toSendCodeResult(dto: UniformSendResponseDto): SendCodeResult {
  return {
    expiresInSeconds: dto.expiresInSeconds,
    resendAfterSeconds: dto.resendAfterSeconds,
    message: dto.message,
  }
}

export function toPrincipal(dto: PrincipalDto): Principal {
  return {
    userId: dto.userId,
    participant: dto.participant,
  }
}

export function toAuthTokens(dto: TokenResponseDto): AuthTokens {
  return {
    accessToken: dto.accessToken,
    refreshToken: dto.refreshToken,
    tokenType: dto.tokenType,
    expiresInSeconds: dto.expiresInSeconds,
  }
}

export function toAuthSession(dto: TokenResponseDto): AuthSession {
  return {
    tokens: toAuthTokens(dto),
    principal: toPrincipal(dto.principal),
  }
}
