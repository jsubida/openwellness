// Tests for OtpInput — mirrors OtpInputField.kt digit-filter / fill callback behaviour.
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'

import { OtpInput } from './OtpInput'

// Controlled harness so the input reflects typed values.
function Harness({
  onFilled,
  error,
  disabled,
}: {
  onFilled?: (code: string) => void
  error?: boolean
  disabled?: boolean
}) {
  const [value, setValue] = useState('')
  return (
    <OtpInput
      value={value}
      onChange={setValue}
      onFilled={onFilled}
      error={error}
      disabled={disabled}
    />
  )
}

describe('OtpInput', () => {
  it('filters out non-digit characters and keeps only digits', async () => {
    // Use the stateful Harness so the controlled input reflects typed chars.
    const onFilled = vi.fn()
    render(<Harness onFilled={onFilled} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, 'a1b2')
    // Value shown in cells should contain only digits.
    const cells = document.querySelectorAll('[data-otp-cell]')
    const displayed = Array.from(cells)
      .map((c) => c.textContent)
      .join('')
    expect(/^\d*$/.test(displayed)).toBe(true)
    // The input's actual value should be '12'.
    expect(input).toHaveValue('12')
  })

  it('slices value to 6 digits maximum', async () => {
    // Harness starts at '' and we pre-fill via typing.
    render(<Harness />)
    const input = screen.getByRole('textbox')
    // Type 9 digits; only 6 should be kept.
    await userEvent.type(input, '123456789')
    expect(input).toHaveValue('123456')
  })

  it('fires onFilled exactly once when the 6th digit is typed', async () => {
    const onFilled = vi.fn()
    render(<Harness onFilled={onFilled} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, '123456')
    expect(onFilled).toHaveBeenCalledTimes(1)
    expect(onFilled).toHaveBeenCalledWith('123456')
  })

  it('does not re-fire onFilled if already at 6 digits and more characters are typed', async () => {
    const onFilled = vi.fn()
    render(<Harness onFilled={onFilled} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, '123456')
    // Typing more should not fire again (already capped at 6)
    await userEvent.type(input, '7')
    expect(onFilled).toHaveBeenCalledTimes(1)
  })

  it('fires onFilled again after value drops below 6 and reaches 6 again', async () => {
    const onFilled = vi.fn()
    render(<Harness onFilled={onFilled} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, '123456')
    expect(onFilled).toHaveBeenCalledTimes(1)
    // Delete a digit then retype
    await userEvent.type(input, '{Backspace}7')
    expect(onFilled).toHaveBeenCalledTimes(2)
  })

  // userEvent.paste writes via onChange — the component has no separate onPaste path.
  it('fires onFilled when pasting exactly 6 digits', async () => {
    const onFilled = vi.fn()
    render(<Harness onFilled={onFilled} />)
    const input = screen.getByRole('textbox')
    await userEvent.click(input)
    await userEvent.paste('123456')
    expect(onFilled).toHaveBeenCalledTimes(1)
    expect(onFilled).toHaveBeenCalledWith('123456')
  })

  it('sanitises a mixed paste and fires onFilled with 6 clean digits', async () => {
    const onFilled = vi.fn()
    render(<Harness onFilled={onFilled} />)
    const input = screen.getByRole('textbox')
    await userEvent.click(input)
    await userEvent.paste('12 34-56')
    expect(onFilled).toHaveBeenCalledTimes(1)
    expect(onFilled).toHaveBeenCalledWith('123456')
  })

  it('applies error border class to display cells when error prop is true', async () => {
    const { container } = render(
      <OtpInput value="123" onChange={vi.fn()} error={true} />,
    )
    const cells = container.querySelectorAll('[data-otp-cell]')
    expect(cells).toHaveLength(6)
    cells.forEach((cell) => {
      expect(cell.className).toMatch(/border-error/)
    })
  })

  it('blocks input when disabled', async () => {
    const onChange = vi.fn()
    render(<OtpInput value="" onChange={onChange} disabled={true} />)
    const input = screen.getByRole('textbox')
    await userEvent.type(input, '123')
    expect(onChange).not.toHaveBeenCalled()
  })
})
