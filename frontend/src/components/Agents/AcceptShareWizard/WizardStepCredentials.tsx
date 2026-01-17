import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import type { PendingSharePublic } from "@/client"
import { CheckCircle, AlertCircle } from "lucide-react"

interface WizardStepCredentialsProps {
  share: PendingSharePublic
  credentialsData: Record<string, Record<string, string>>
  onChange: (data: Record<string, Record<string, string>>) => void
  onNext: () => void
  onBack: () => void
}

export function WizardStepCredentials({
  share,
  credentialsData,
  onChange,
  onNext,
  onBack,
}: WizardStepCredentialsProps) {
  const credentials = share.credentials_required || []

  const handleFieldChange = (credName: string, field: string, value: string) => {
    onChange({
      ...credentialsData,
      [credName]: {
        ...(credentialsData[credName] || {}),
        [field]: value,
      },
    })
  }

  // Group credentials by status
  const shareableCredentials = credentials.filter((c) => c.allow_sharing)
  const setupRequiredCredentials = credentials.filter((c) => !c.allow_sharing)

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        This agent requires the following credentials. Some are shared by the
        owner, while others need to be set up with your own values.
      </p>

      {/* Shareable credentials (ready) */}
      {shareableCredentials.length > 0 && (
        <div className="space-y-3">
          <h4 className="font-medium text-green-700 flex items-center gap-2">
            <CheckCircle className="h-4 w-4" />
            Ready to Use ({shareableCredentials.length})
          </h4>
          <div className="space-y-2">
            {shareableCredentials.map((cred) => (
              <div
                key={cred.name}
                className="flex items-center justify-between p-3 bg-green-50 dark:bg-green-950/20 rounded-lg border border-green-200 dark:border-green-800"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium">{cred.name}</span>
                  <Badge variant="outline" className="text-xs">
                    {cred.type}
                  </Badge>
                </div>
                <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                  Shared by owner
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Setup required credentials */}
      {setupRequiredCredentials.length > 0 && (
        <div className="space-y-3">
          <h4 className="font-medium text-yellow-700 dark:text-yellow-500 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            Setup Required ({setupRequiredCredentials.length})
          </h4>
          <p className="text-xs text-muted-foreground">
            These credentials contain personal data and need to be configured
            with your own values. You can skip for now and set them up later.
          </p>
          <div className="space-y-4">
            {setupRequiredCredentials.map((cred) => (
              <div
                key={cred.name}
                className="p-4 bg-yellow-50 dark:bg-yellow-950/20 rounded-lg border border-yellow-200 dark:border-yellow-800"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{cred.name}</span>
                    <Badge variant="outline" className="text-xs">
                      {cred.type}
                    </Badge>
                  </div>
                </div>

                <div className="space-y-3">
                  <div>
                    <Label htmlFor={`${cred.name}-value`}>Value</Label>
                    <Input
                      id={`${cred.name}-value`}
                      type="password"
                      placeholder="Enter credential value"
                      value={credentialsData[cred.name]?.value || ""}
                      onChange={(e) =>
                        handleFieldChange(cred.name, "value", e.target.value)
                      }
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex justify-between pt-4 border-t">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onNext}>
            Skip for now
          </Button>
          <Button onClick={onNext}>Continue</Button>
        </div>
      </div>
    </div>
  )
}
