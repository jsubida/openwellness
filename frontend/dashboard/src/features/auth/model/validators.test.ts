// Tests for validators.ts — mirrors ValidationUseCasesTest.kt
import { describe, expect, it } from 'vitest'

import { validateEmail, validateOtpCode } from './validators'

describe('validateEmail', () => {
  it('accepts a well-formed email', () => {
    const result = validateEmail('person@example.com')
    expect(result.ok).toBe(true)
  })

  it('trims surrounding whitespace before validating', () => {
    const result = validateEmail('  person@example.com  ')
    expect(result.ok).toBe(true)
  })

  it('rejects an email missing the @ sign', () => {
    const result = validateEmail('personexample.com')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidEmail' } })
  })

  it('rejects a blank string', () => {
    const result = validateEmail('   ')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidEmail' } })
  })

  it('rejects an empty string', () => {
    const result = validateEmail('')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidEmail' } })
  })
})

describe('validateOtpCode', () => {
  it('accepts exactly six digits', () => {
    const result = validateOtpCode('123456')
    expect(result.ok).toBe(true)
  })

  it('rejects fewer than six digits', () => {
    const result = validateOtpCode('12345')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidCode' } })
  })

  it('rejects a six-character code containing a letter', () => {
    const result = validateOtpCode('12a456')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidCode' } })
  })

  it('rejects more than six digits', () => {
    const result = validateOtpCode('1234567')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidCode' } })
  })

  it('rejects a blank string', () => {
    const result = validateOtpCode('')
    expect(result).toEqual({ ok: false, error: { kind: 'InvalidCode' } })
  })
})
