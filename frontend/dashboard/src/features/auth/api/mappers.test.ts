// Pure mapping tests. Mirrors mapping assertions in OpenWellnessAuthRepositoryTest.kt.
import { describe, expect, it } from 'vitest'

import { toAuthSession, toPrincipal, toSendCodeResult } from './mappers'
import type {
  PrincipalDto,
  TokenResponseDto,
  UniformSendResponseDto,
} from './dtos'

describe('toSendCodeResult', () => {
  it('maps all fields from UniformSendResponseDto', () => {
    const dto: UniformSendResponseDto = {
      status: 'OK',
      message: 'Check your inbox',
      expiresInSeconds: 300,
      resendAfterSeconds: 60,
    }
    expect(toSendCodeResult(dto)).toEqual({
      expiresInSeconds: 300,
      resendAfterSeconds: 60,
      message: 'Check your inbox',
    })
  })
})

describe('toPrincipal', () => {
  it('maps userId and non-null participant', () => {
    const dto: PrincipalDto = { userId: 'u1', participant: 'participants/42' }
    expect(toPrincipal(dto)).toEqual({
      userId: 'u1',
      participant: 'participants/42',
    })
  })

  it('maps null participant', () => {
    const dto: PrincipalDto = { userId: 'u2', participant: null }
    expect(toPrincipal(dto)).toEqual({ userId: 'u2', participant: null })
  })
})

describe('toAuthSession', () => {
  const TOKEN_DTO: TokenResponseDto = {
    accessToken: 'access-1',
    tokenType: 'Bearer',
    expiresInSeconds: 900,
    refreshToken: 'refresh-1',
    principal: { userId: 'u1', participant: 'participants/42' },
  }

  it('maps the full TokenResponseDto to an AuthSession', () => {
    expect(toAuthSession(TOKEN_DTO)).toEqual({
      tokens: {
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
        tokenType: 'Bearer',
        expiresInSeconds: 900,
      },
      principal: {
        userId: 'u1',
        participant: 'participants/42',
      },
    })
  })

  it('preserves a null participant in the session', () => {
    const dto: TokenResponseDto = {
      ...TOKEN_DTO,
      principal: { userId: 'u3', participant: null },
    }
    const session = toAuthSession(dto)
    expect(session.principal.participant).toBeNull()
  })
})
