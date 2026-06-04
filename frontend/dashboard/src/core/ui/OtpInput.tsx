// Mirrors OtpInputField.kt — six-cell OTP entry backed by a single hidden input
// so paste and iOS/Android OTP autofill work natively.
import { useRef, useEffect, useState } from 'react'

import { cn } from '@/core/lib/cn'

interface OtpInputProps {
  value: string
  onChange: (v: string) => void
  /** Called exactly once when the value transitions to 6 digits; resets when it drops below 6. */
  onFilled?: (code: string) => void
  error?: boolean
  disabled?: boolean
  autoFocus?: boolean
  'aria-describedby'?: string
}

const LENGTH = 6

/**
 * Six-cell OTP input. A visually-hidden real `<input>` overlays the display
 * cells so paste and native OTP autofill (iOS/Android) work transparently.
 *
 * Mobile mirror — OtpInputField.kt:
 *   • Cell size: 44×52dp → 44px × 52px (w-11 / h-[52px])
 *   • Cell gap: 8dp → gap-2
 *   • Border radius: shapes.small = 8dp → rounded-sm
 *   • Error border: 2px border-error on all cells
 *   • Active cell (caret position): primary 2px border + ring
 *   • Digit colour: onSurface (default foreground)
 *   • Text style: headlineSmall → text-xl font-medium
 */
function OtpInput({
  value,
  onChange,
  onFilled,
  error = false,
  disabled = false,
  autoFocus = false,
  'aria-describedby': ariaDescribedBy,
}: OtpInputProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [focused, setFocused] = useState(false)

  // Track whether we've already fired onFilled for the current filled run so
  // we only call it on the transition TO 6 digits, not on every render.
  // useRef (not state) is intentional — refs survive StrictMode double-mount,
  // so a value already at length 6 on mount can't double-fire `onFilled`.
  const filledRef = useRef(false)

  useEffect(() => {
    if (value.length === LENGTH) {
      if (!filledRef.current) {
        filledRef.current = true
        onFilled?.(value)
      }
    } else {
      // Reset so the next fill will fire again.
      filledRef.current = false
    }
  }, [value, onFilled])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (disabled) return
    const clean = e.target.value.replace(/\D/g, '').slice(0, LENGTH)
    onChange(clean)
    // Reset caret to end so the active-cell highlight can't desync from
    // mid-string caret moves (e.g. user clicking between cells).
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (el) el.setSelectionRange(clean.length, clean.length)
    })
  }

  function focusInput() {
    inputRef.current?.focus()
  }

  // The active caret cell = value.length (the first empty cell), capped at LENGTH-1.
  const activeIndex = Math.min(value.length, LENGTH - 1)

  return (
    <div
      className="relative inline-flex items-center"
      onClick={focusInput}
      role="presentation"
    >
      {/* Hidden real input — positioned over all cells so it captures focus,
          clipboard events, and IME. opacity-0 + absolute keeps it screen-reader
          visible and lets browsers attach autofill affordances. */}
      <input
        ref={inputRef}
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        aria-label="6-digit code"
        value={value}
        onChange={handleChange}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-describedby={ariaDescribedBy}
        className="absolute inset-0 z-10 h-full w-full cursor-default opacity-0"
        style={{ letterSpacing: 0 }}
      />

      {/* Display cells — purely visual. */}
      <div className="flex gap-2">
        {Array.from({ length: LENGTH }, (_, i) => {
          const digit = value[i] ?? ''
          const isActive = focused && i === activeIndex && !digit
          const isFilled = digit !== ''

          return (
            <div
              key={i}
              data-otp-cell={i}
              className={cn(
                // Dimensions & layout (OtpInputField.kt: 44×52dp, shapes.small)
                'flex h-[52px] w-11 items-center justify-center rounded-sm',
                // Border — 150ms transition
                'border transition-colors duration-150',
                // State-driven border colours
                error
                  ? 'border-2 border-error'
                  : isActive
                    ? 'border-2 border-primary ring-2 ring-primary/20'
                    : isFilled
                      ? 'border-primary'
                      : 'border-outline',
              )}
            >
              <span className="text-xl font-medium text-on-surface">
                {digit}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export { OtpInput }
