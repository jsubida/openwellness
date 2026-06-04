// Tests for core/api/url.ts (slash-route URL builder).
import { describe, it, expect } from 'vitest'

import { buildApiUrl } from './url'

describe('buildApiUrl', () => {
  it('keeps the literal colon in a slash-style verb', () => {
    const url = buildApiUrl('auth:sendLoginCode', 'http://127.0.0.1:8000/v1')
    expect(url).toBe('http://127.0.0.1:8000/v1/auth:sendLoginCode')
  })

  it('handles a base WITH a trailing slash', () => {
    const url = buildApiUrl('auth:verifyLoginCode', 'http://127.0.0.1:8000/v1/')
    expect(url).toBe('http://127.0.0.1:8000/v1/auth:verifyLoginCode')
  })

  it('handles a base WITHOUT a trailing slash', () => {
    const url = buildApiUrl('auth:refreshToken', 'http://127.0.0.1:8000/v1')
    expect(url).toBe('http://127.0.0.1:8000/v1/auth:refreshToken')
  })

  it('does not parse the verb prefix as a URL scheme', () => {
    const url = buildApiUrl('auth:sendLoginCode', 'https://api.example.com/v1')
    expect(url).toBe('https://api.example.com/v1/auth:sendLoginCode')
    expect(url.startsWith('https://api.example.com/v1/')).toBe(true)
  })

  it('tolerates a leading slash on the path', () => {
    const url = buildApiUrl('/auth:sendLoginCode', 'http://127.0.0.1:8000/v1')
    expect(url).toBe('http://127.0.0.1:8000/v1/auth:sendLoginCode')
  })
})
