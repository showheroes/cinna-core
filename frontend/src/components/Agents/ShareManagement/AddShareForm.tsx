import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Loader2, CheckCircle } from "lucide-react"

import { AgentSharesService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Alert, AlertDescription } from "@/components/ui/alert"

interface AddShareFormProps {
  agentId: string
  onSuccess: () => void
}

export function AddShareForm({ agentId, onSuccess }: AddShareFormProps) {
  const [email, setEmail] = useState("")
  const [shareMode, setShareMode] = useState<"user" | "builder">("user")
  const [success, setSuccess] = useState(false)

  const shareMutation = useMutation({
    mutationFn: () =>
      AgentSharesService.shareAgent({
        agentId,
        requestBody: {
          shared_with_email: email,
          share_mode: shareMode,
        },
      }),
    onSuccess: () => {
      setSuccess(true)
      setEmail("")
      onSuccess()
      setTimeout(() => setSuccess(false), 3000)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    shareMutation.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Email input */}
      <div className="space-y-2">
        <Label htmlFor="email">User Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="user@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <p className="text-xs text-muted-foreground">
          The user must have an existing account.
        </p>
      </div>

      {/* Share mode selection */}
      <div className="space-y-3">
        <Label>Access Level</Label>
        <RadioGroup value={shareMode} onValueChange={(v) => setShareMode(v as "user" | "builder")}>
          <div className="flex items-start space-x-3 p-3 border rounded-lg">
            <RadioGroupItem value="user" id="user" className="mt-1" />
            <div>
              <Label htmlFor="user" className="font-medium cursor-pointer">User Access</Label>
              <p className="text-sm text-muted-foreground">
                Can use the agent in conversation mode. Configuration is read-only.
              </p>
            </div>
          </div>
          <div className="flex items-start space-x-3 p-3 border rounded-lg">
            <RadioGroupItem value="builder" id="builder" className="mt-1" />
            <div>
              <Label htmlFor="builder" className="font-medium cursor-pointer">Builder Access</Label>
              <p className="text-sm text-muted-foreground">
                Full access to modify prompts, scripts, and configuration.
              </p>
            </div>
          </div>
        </RadioGroup>
      </div>

      {/* Error display */}
      {shareMutation.error && (
        <Alert variant="destructive">
          <AlertDescription>
            {(shareMutation.error as Error).message || "Failed to share agent"}
          </AlertDescription>
        </Alert>
      )}

      {/* Success message */}
      {success && (
        <Alert className="border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950">
          <CheckCircle className="h-4 w-4 text-green-600 dark:text-green-400" />
          <AlertDescription className="text-green-800 dark:text-green-200">
            Share created successfully! The user will see it in their pending shares.
          </AlertDescription>
        </Alert>
      )}

      {/* Submit button */}
      <Button type="submit" disabled={shareMutation.isPending || !email}>
        {shareMutation.isPending ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Sharing...
          </>
        ) : (
          "Share Agent"
        )}
      </Button>
    </form>
  )
}
