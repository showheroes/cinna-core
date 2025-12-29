import { Loader2, AlertCircle, FileText } from "lucide-react"
import { Button } from "@/components/ui/button"

export function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
      <Loader2 className="h-8 w-8 animate-spin" />
      <p className="text-sm">Loading workspace...</p>
    </div>
  )
}

interface ErrorStateProps {
  error: Error | unknown
  onRetry: () => void
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-4">
      <AlertCircle className="h-8 w-8 text-destructive" />
      <div className="text-center">
        <p className="text-sm font-medium mb-1">Failed to load workspace</p>
        <p className="text-xs">{error instanceof Error ? error.message : "Unknown error"}</p>
      </div>
      <Button size="sm" variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-4">
      <FileText className="h-8 w-8" />
      <p className="text-sm text-center">No files found in this section</p>
    </div>
  )
}

export function NoEnvironmentState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-4">
      <AlertCircle className="h-8 w-8" />
      <p className="text-sm text-center">No environment available for this session</p>
    </div>
  )
}
