import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import type { PendingSharePublic } from "@/client"
import { CheckCircle, AlertTriangle, Loader2, User } from "lucide-react"
import type { CredentialSelection } from "./AcceptShareWizard"

interface WizardStepConfirmProps {
  share: PendingSharePublic
  credentialSelections: Record<string, CredentialSelection>
  onAccept: () => void
  onBack: () => void
  isLoading: boolean
  error?: string
}

export function WizardStepConfirm({
  share,
  credentialSelections,
  onAccept,
  onBack,
  isLoading,
  error,
}: WizardStepConfirmProps) {
  const credentials = share.credentials_required || []

  // Count credential statuses
  const sharedCount = credentials.filter((c) => {
    const selection = credentialSelections[c.name]
    // Using shared: shareable credential with no override selection
    return c.allow_sharing && (!selection?.selectedCredentialId || selection.selectedCredentialId === null)
  }).length

  const ownCredentialCount = Object.values(credentialSelections).filter(
    (s) => s.selectedCredentialId && s.selectedCredentialId !== "__create_new__"
  ).length

  const nonShareableCredentials = credentials.filter((c) => !c.allow_sharing)
  const skippedCount = nonShareableCredentials.filter((c) => {
    const selection = credentialSelections[c.name]
    return !selection?.selectedCredentialId || selection.selectedCredentialId === "__create_new__"
  }).length

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
            {sharedCount > 0 && (
              <li className="flex items-center gap-2 text-green-700 dark:text-green-400">
                <CheckCircle className="h-4 w-4" />
                {sharedCount} using owner's shared credentials
              </li>
            )}
            {ownCredentialCount > 0 && (
              <li className="flex items-center gap-2 text-blue-700 dark:text-blue-400">
                <User className="h-4 w-4" />
                {ownCredentialCount} using your own credentials
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
