// Mirrors EmailTextField.kt — labelled email input with ImeAction.Done (Enter key)
// and an inline error slot wired for accessibility.
import { useId } from 'react'

import { Input } from '@/core/ui/input'
import { Label } from '@/core/ui/label'
import { ErrorText } from '@/core/ui/ErrorText'

interface EmailFieldProps {
  value: string
  onChange: (value: string) => void
  error?: string | null
  /**
   * Fired when Enter is pressed — mirrors ImeAction.Done.
   * Inside a `<form>`, pressing Enter ALSO submits the form, so callers should
   * use one or the other (or call `e.preventDefault()` in their `onSubmit`),
   * not both, to avoid double-handling.
   */
  onEnter?: () => void
  disabled?: boolean
  autoFocus?: boolean
  id?: string
  label?: string
}

/**
 * Labelled email input. Fires `onEnter` on Enter keydown when provided.
 * When `error` is set, the input gets `aria-invalid` and `aria-describedby`
 * pointing to the `ErrorText` below it.
 */
function EmailField({
  value,
  onChange,
  error,
  onEnter,
  disabled,
  autoFocus,
  id: idProp,
  label = 'Email',
}: EmailFieldProps) {
  const autoId = useId()
  const id = idProp ?? autoId
  const errorId = `${id}-error`
  const hasError = Boolean(error)

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && onEnter) {
      onEnter()
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="email"
        autoComplete="email"
        inputMode="email"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-invalid={hasError ? true : undefined}
        aria-describedby={hasError ? errorId : undefined}
      />
      {hasError && error && (
        <ErrorText id={errorId} className="mt-0">
          {error}
        </ErrorText>
      )}
    </div>
  )
}

export { EmailField }
