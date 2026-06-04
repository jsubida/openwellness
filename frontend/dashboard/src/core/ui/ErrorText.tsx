// Mirrors ErrorText.kt — inline error-coloured helper text for field validation.
import { cn } from '@/core/lib/cn'

interface ErrorTextProps {
  children: React.ReactNode
  id?: string
  className?: string
}

/** Small error-coloured paragraph. Announces itself as an alert to screen readers. */
function ErrorText({ children, id, className }: ErrorTextProps) {
  return (
    <p id={id} role="alert" className={cn('text-sm text-error', className)}>
      {children}
    </p>
  )
}

export { ErrorText }
