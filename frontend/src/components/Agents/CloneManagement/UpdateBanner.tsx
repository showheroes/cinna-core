import { RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

interface UpdateBannerProps {
  pendingSince?: string
  onApply: () => void
  isLoading: boolean
}

export function UpdateBanner({ pendingSince, onApply, isLoading }: UpdateBannerProps) {
  return (
    <Alert className="mb-4 border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950">
      <RefreshCw className="h-4 w-4 text-blue-600 dark:text-blue-400" />
      <AlertTitle className="text-blue-800 dark:text-blue-200">Update Available</AlertTitle>
      <AlertDescription className="flex items-center justify-between">
        <span className="text-blue-700 dark:text-blue-300">
          New changes from the parent agent are available.
          {pendingSince && ` Last updated: ${new Date(pendingSince).toLocaleString()}`}
        </span>
        <Button
          size="sm"
          onClick={onApply}
          disabled={isLoading}
          className="ml-4"
        >
          Apply Update
        </Button>
      </AlertDescription>
    </Alert>
  )
}
