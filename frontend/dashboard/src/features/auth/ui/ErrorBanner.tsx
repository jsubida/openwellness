// Dismissible error banner shared by EmailStep and CodeStep.
// The dismiss button is a SIBLING of the Alert (not a child) so screen readers
// do not re-announce the live region when the button receives focus or is clicked.
import { X } from 'lucide-react'

import { Alert, AlertDescription } from '@/core/ui/alert'
import { Button } from '@/core/ui/button'

interface ErrorBannerProps {
  message: string
  onDismiss: () => void
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div className="relative">
      {/* role="alert" lives on Alert — only the message text is inside the live
          region so focus/click on the dismiss button cannot trigger a re-read. */}
      <Alert variant="destructive">
        <AlertDescription className="pr-6">{message}</AlertDescription>
      </Alert>
      <Button
        type="button"
        variant="ghost"
        size="icon-xs"
        aria-label="Dismiss"
        onClick={onDismiss}
        className="absolute top-2 right-2 text-destructive hover:text-destructive"
      >
        <X />
      </Button>
    </div>
  )
}
