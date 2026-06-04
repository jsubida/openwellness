// Tests for messages.ts — verifies every AuthError variant maps to the expected string
import { describe, expect, it } from 'vitest'

import { authErrorMessage } from './messages'

describe('authErrorMessage', () => {
  it('returns the correct string for InvalidOrExpiredCode', () => {
    const msg = authErrorMessage({ kind: 'InvalidOrExpiredCode' })
    expect(msg).toBe('That code is invalid or has expired.')
  })

  it('returns the correct string for InvalidEmail', () => {
    const msg = authErrorMessage({ kind: 'InvalidEmail' })
    expect(msg).toBe('Enter a valid email address.')
  })

  it('returns the correct string for InvalidCode', () => {
    const msg = authErrorMessage({ kind: 'InvalidCode' })
    expect(msg).toBe('Enter the 6-digit code.')
  })

  it('interpolates the retry seconds in RateLimited message', () => {
    const msg = authErrorMessage({ kind: 'RateLimited', retryAfterSeconds: 42 })
    expect(msg).toBe('Too many attempts. Please wait 42s and try again.')
  })

  it('returns the correct string for Unauthorized', () => {
    const msg = authErrorMessage({ kind: 'Unauthorized' })
    expect(msg).toBe('Your session has expired. Please sign in again.')
  })

  it('returns the correct string for NotAuthorized', () => {
    const msg = authErrorMessage({ kind: 'NotAuthorized' })
    expect(msg).toBe(
      "This account isn't authorized for the coaching dashboard.",
    )
  })

  it('returns the correct string for NoInternet', () => {
    const msg = authErrorMessage({ kind: 'NoInternet' })
    expect(msg).toBe(
      'No internet connection. Check your network and try again.',
    )
  })

  it('returns the correct string for Server', () => {
    const msg = authErrorMessage({ kind: 'Server' })
    expect(msg).toBe(
      "We're having trouble reaching the server. Please try again later.",
    )
  })

  it('returns the correct string for Unknown', () => {
    const msg = authErrorMessage({ kind: 'Unknown' })
    expect(msg).toBe('Something went wrong. Please try again.')
  })
})
