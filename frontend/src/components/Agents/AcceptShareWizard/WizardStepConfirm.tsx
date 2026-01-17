import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import type { PendingSharePublic } from "@/client"
import { CheckCircle, AlertTriangle, Loader2 } from "lucide-react"

interface WizardStepConfirmProps {
  share: PendingSharePublic
  credentialsData: Record<string, Record<string, string>>
  onAccept: () => void
  onBack: () => void
  isLoading: boolean
  error?: string
}

export function WizardStepConfirm({
  share,
  credentialsData,
  onAccept,
  onBack,
  isLoading,
  error,
}: WizardStepConfirmProps) {
  const credentials = share.credentials_required || []
  const setupRequired = credentials.filter((c) => !c.allow_sharing)
  const configuredCount = Object.keys(credentialsData).filter(
    (key) => credentialsData[key]?.value
  ).length
  const skippedCount = setupRequired.length - configuredCount

  return (
    <div className="space-y-6">
      <div className="p-4 bg-muted rounded-lg">
        <h3 className="font-semibold mb-4">Summary</h3>

        <dl className="space-y-3 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Agent</dt>
            <dd className="font-medium">{share.original_agent_name}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Access Level</dt>
            <dd className="font-medium">
              {share.share_mode === "builder" ? "Builder" : "User"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Shared By</dt>
            <dd className="font-medium">{share.shared_by_email}</dd>
          </div>
        </dl>
      </div>

      {/* Credentials summary */}
      {credentials.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium">Credentials</h4>
          <ul className="text-sm space-y-1">
            {credentials.filter((c) => c.allow_sharing).length > 0 && (
              <li className="flex items-center gap-2 text-green-700 dark:text-green-400">
                <CheckCircle className="h-4 w-4" />
                {credentials.filter((c) => c.allow_sharing).length} shared
                credentials ready
              </li>
            )}
            {configuredCount > 0 && (
              <li className="flex items-center gap-2 text-green-700 dark:text-green-400">
                <CheckCircle className="h-4 w-4" />
                {configuredCount} credentials configured
              </li>
            )}
            {skippedCount > 0 && (
              <li className="flex items-center gap-2 text-yellow-700 dark:text-yellow-400">
                <AlertTriangle className="h-4 w-4" />
                {skippedCount} credentials skipped (setup later)
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Warning for skipped credentials */}
      {skippedCount > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Some credentials were skipped. The agent may not be fully functional
            until you configure them in the agent settings.
          </AlertDescription>
        </Alert>
      )}

      {/* Error display */}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Actions */}
      <div className="flex justify-between pt-4 border-t">
        <Button variant="outline" onClick={onBack} disabled={isLoading}>
          Back
        </Button>
        <Button onClick={onAccept} disabled={isLoading}>
          {isLoading ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Creating Agent...
            </>
          ) : (
            "Accept and Create Agent"
          )}
        </Button>
      </div>
    </div>
  )
}
