// Tests for LoadingButton — mirrors Buttons.kt LoadingButton disabled-during-load behaviour.
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { LoadingButton } from './LoadingButton'

describe('LoadingButton', () => {
  it('renders as disabled and aria-busy when loading', () => {
    render(<LoadingButton loading>Save</LoadingButton>)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-busy', 'true')
  })

  it('renders a spinner when loading', () => {
    render(<LoadingButton loading>Save</LoadingButton>)
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
  })

  it('keeps the label visible alongside the spinner when loading', () => {
    render(<LoadingButton loading>Save</LoadingButton>)
    expect(screen.getByText('Save')).toBeInTheDocument()
  })

  it('fires onClick when not loading and button is clicked', async () => {
    const onClick = vi.fn()
    render(<LoadingButton onClick={onClick}>Save</LoadingButton>)
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('does not fire onClick when loading and button is clicked', async () => {
    const onClick = vi.fn()
    render(
      <LoadingButton loading onClick={onClick}>
        Save
      </LoadingButton>,
    )
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })
})
