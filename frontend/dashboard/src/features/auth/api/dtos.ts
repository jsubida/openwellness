// Mirrors mobile AuthDtos.kt (feature/auth/data/src/commonMain/.../dto/AuthDtos.kt)

// --------------------------------------------------------------------------- //
// Requests — camelCase property names == wire keys
// --------------------------------------------------------------------------- //

export interface SendLoginCodeRequestDto {
  email: string
}

export interface VerifyLoginCodeRequestDto {
  email: string
  code: string
}

/** Revoke body: either { refreshToken } or { all: true }. */
export interface RevokeTokenRequestDto {
  refreshToken?: string
  all?: boolean
}

// --------------------------------------------------------------------------- //
// Responses
// --------------------------------------------------------------------------- //

export interface UniformSendResponseDto {
  status: string
  message: string
  expiresInSeconds: number
  resendAfterSeconds: number
}

export interface PrincipalDto {
  userId: string
  participant: string | null
}

export interface TokenResponseDto {
  accessToken: string
  tokenType: string
  expiresInSeconds: number
  refreshToken: string
  principal: PrincipalDto
}

export interface RevokeResponseDto {
  status: string
}
