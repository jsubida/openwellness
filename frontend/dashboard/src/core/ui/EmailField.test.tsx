// Tests for EmailField — mirrors EmailTextField.kt ImeAction.Done + error slot behaviour.
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { EmailField } from './EmailField'

describe('EmailField', () => {
  it('fires onEnter when Enter key is pressed', async () => {
    const onEnter = vi.fn()
    render(<EmailField value="" onChange={vi.fn()} onEnter={onEnter} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, '{Enter}')
    expect(onEnter).toHaveBeenCalledTimes(1)
  })

  it('calls onChange with the typed string value', async () => {
    const onChange = vi.fn()
    render(<EmailField value="" onChange={onChange} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'a')
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it('renders error message with role="alert" when error prop is set', () => {
    render(
      <EmailField value="" onChange={vi.fn()} error="Invalid email address" />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid email address')
  })

  it('marks input as aria-invalid when error prop is set', () => {
    render(
      <EmailField value="" onChange={vi.fn()} error="Invalid email address" />,
    )
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
  })

  it('links input to error via aria-describedby when error is set', () => {
    render(
      <EmailField value="" onChange={vi.fn()} error="Invalid email address" />,
    )
    const input = screen.getByRole('textbox')
    const describedById = input.getAttribute('aria-describedby')
    expect(describedById).toBeTruthy()
    const errorEl = document.getElementById(describedById!)
    expect(errorEl).toBeInTheDocument()
    expect(errorEl).toHaveTextContent('Invalid email address')
  })

  it('does not render error message when error prop is absent', () => {
    render(<EmailField value="" onChange={vi.fn()} />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
