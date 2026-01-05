import { Control } from "react-hook-form"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { CredentialsService } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface OAuthCredentialFieldsProps {
  control: Control<any>
  credentialType: string
  credentialId?: string
}

// Map credential type to display name
const CREDENTIAL_TYPE_NAMES: Record<string, string> = {
  gmail_oauth: "Gmail",
  gmail_oauth_readonly: "Gmail (Read-Only)",
  gdrive_oauth: "Google Drive",
  gdrive_oauth_readonly: "Google Drive (Read-Only)",
  gcalendar_oauth: "Google Calendar",
  gcalendar_oauth_readonly: "Google Calendar (Read-Only)",
}

export function OAuthCredentialFields({
  control,
  credentialType,
  credentialId,
}: OAuthCredentialFieldsProps) {
  const displayName = CREDENTIAL_TYPE_NAMES[credentialType] || "Google Service"
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // Fetch OAuth metadata if credential already exists
  const { data: metadata, isLoading: isLoadingMetadata } = useQuery({
    queryKey: ["oauthMetadata", credentialId],
    queryFn: () =>
      credentialId
        ? CredentialsService.getOauthMetadata({ credentialId })
        : Promise.resolve(null),
    enabled: !!credentialId,
    refetchInterval: false,
  })

  // Mutation to initiate OAuth flow
  const authorizeMutation = useMutation({
    mutationFn: () =>
      CredentialsService.oauthAuthorize({ credentialId: credentialId! }),
    onSuccess: (data) => {
      // Open authorization URL in popup or redirect
      const authUrl = data.authorization_url
      const width = 600
      const height = 700
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2

      const popup = window.open(
        authUrl,
        "Google OAuth",
        `width=${width},height=${height},left=${left},top=${top}`
      )

      if (!popup) {
        showErrorToast("Failed to open authorization window. Please allow popups.")
        return
      }

      // Poll for popup closure or success
      const checkPopup = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkPopup)
          // Refresh metadata after OAuth flow completes
          queryClient.invalidateQueries({ queryKey: ["oauthMetadata", credentialId] })
          queryClient.invalidateQueries({ queryKey: ["credentials"] })
          queryClient.invalidateQueries({ queryKey: ["credential", credentialId] })
        }
      }, 500)
    },
    onError: handleError.bind(showErrorToast),
  })

  // Mutation to refresh OAuth token
  const refreshMutation = useMutation({
    mutationFn: () =>
      CredentialsService.refreshOauthToken({ credentialId: credentialId! }),
    onSuccess: () => {
      showSuccessToast("OAuth token refreshed successfully")
      queryClient.invalidateQueries({ queryKey: ["oauthMetadata", credentialId] })
      queryClient.invalidateQueries({ queryKey: ["credentials"] })
      queryClient.invalidateQueries({ queryKey: ["credential", credentialId] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const handleGrantFromGoogle = () => {
    if (!credentialId) {
      showErrorToast("Please save the credential first before authorizing")
      return
    }
    authorizeMutation.mutate()
  }

  const handleRefreshToken = () => {
    if (!credentialId) {
      return
    }
    refreshMutation.mutate()
  }

  const isAuthorized = metadata && metadata.user_email
  const isExpiringSoon = metadata?.expires_at
    ? metadata.expires_at < Date.now() / 1000 + 86400 // Expires within 24 hours
    : false

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>OAuth Authorization</CardTitle>
          <CardDescription>
            Grant access to your {displayName} account
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-2">
            <Button
              type="button"
              variant={isAuthorized ? "outline" : "default"}
              onClick={handleGrantFromGoogle}
              disabled={!credentialId || authorizeMutation.isPending}
              className="w-full"
            >
              {authorizeMutation.isPending
                ? "Opening authorization..."
                : isAuthorized
                  ? "Re-authorize with Google"
                  : "Grant from Google"}
            </Button>

            {isAuthorized && (
              <Button
                type="button"
                variant="outline"
                onClick={handleRefreshToken}
                disabled={refreshMutation.isPending}
                className="w-full"
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                {refreshMutation.isPending ? "Refreshing..." : "Refresh Token"}
              </Button>
            )}

            {!credentialId && (
              <p className="text-sm text-muted-foreground">
                Please save the credential first, then you can authorize with Google.
              </p>
            )}
          </div>

          {/* OAuth Metadata Display */}
          {credentialId && (
            <div className="mt-4 space-y-2 rounded-lg border p-4 bg-muted/50">
              <h4 className="text-sm font-medium">Authorization Status</h4>
              {isLoadingMetadata ? (
                <div className="text-sm text-muted-foreground">Loading...</div>
              ) : isAuthorized ? (
                <div className="space-y-1 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">Status:</span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-1 text-xs font-medium ${
                        isExpiringSoon
                          ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
                          : "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                      }`}
                    >
                      {isExpiringSoon ? "Expires Soon" : "Active"}
                    </span>
                  </div>
                  <div className="text-muted-foreground">
                    <span className="font-medium">Email:</span> {metadata.user_email}
                  </div>
                  {metadata.user_name && (
                    <div className="text-muted-foreground">
                      <span className="font-medium">Name:</span> {metadata.user_name}
                    </div>
                  )}
                  {metadata.expires_at && (
                    <div className="text-muted-foreground">
                      <span className="font-medium">Expires:</span>{" "}
                      {new Date(metadata.expires_at * 1000).toLocaleString()}
                    </div>
                  )}
                  {metadata.granted_at && (
                    <div className="text-muted-foreground">
                      <span className="font-medium">Granted:</span>{" "}
                      {new Date(metadata.granted_at * 1000).toLocaleString()}
                    </div>
                  )}
                  {metadata.scopes && metadata.scopes.length > 0 && (
                    <div className="text-muted-foreground">
                      <span className="font-medium">Scopes:</span>
                      <ul className="ml-4 mt-1 list-disc text-xs">
                        {metadata.scopes.map((scope, i) => (
                          <li key={i} className="break-all">
                            {scope}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  Not yet authorized. Click "Grant from Google" to authorize.
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
