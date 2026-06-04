// Smoke test for the assembled app shell. With no stored refresh token the
// auth bootstrap resolves to 'unauthenticated' WITHOUT a network call, so the
// landing+login page renders. Full flows arrive with MSW in the next task —
// this stays a single light render check.
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { tokenStorage } from '@/core/auth/tokenStorage'

import App from './App'

beforeEach(() => {
  tokenStorage.clear()
  localStorage.clear()
  window.history.pushState({}, '', '/')
})

describe('App', () => {
  it('renders the landing+login page when unauthenticated', async () => {
    render(<App />)

    expect(
      await screen.findByRole('heading', { name: 'OpenWellness' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
  })
})
