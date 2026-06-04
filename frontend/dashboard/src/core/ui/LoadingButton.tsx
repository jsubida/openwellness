// Mirrors Buttons.kt LoadingButton — filled primary button that shows a spinner
// alongside its label while a request is in-flight and blocks double-submission.
import { Loader2 } from 'lucide-react'

import { Button } from '@/core/ui/button'
import type { buttonVariants } from '@/core/ui/button'
import type { VariantProps } from 'class-variance-authority'

import { cn } from '@/core/lib/cn'

interface LoadingButtonProps
  extends React.ComponentProps<'button'>, VariantProps<typeof buttonVariants> {
  loading?: boolean
}

/**
 * Primary filled button with an inline spinner. While `loading` is true the
 * button is disabled and aria-busy so it cannot be double-submitted. The label
 * stays visible alongside the spinner (web convention vs. mobile swap-only).
 *
 * Mobile mirror: Buttons.kt uses `MaterialTheme.shapes.medium` (12dp) and
 * `heightIn(min = 48.dp)`. We apply `rounded-md` (12px) and `min-h-[48px]`.
 */
function LoadingButton({
  loading = false,
  disabled,
  children,
  className,
  ...props
}: LoadingButtonProps) {
  return (
    <Button
      disabled={disabled || loading}
      aria-busy={loading ? 'true' : undefined}
      className={cn('min-h-[48px] w-full rounded-md', className)}
      {...props}
    >
      {loading && (
        <Loader2
          data-testid="loading-spinner"
          className="size-4 animate-spin"
          aria-hidden="true"
        />
      )}
      {children}
    </Button>
  )
}

export { LoadingButton }
