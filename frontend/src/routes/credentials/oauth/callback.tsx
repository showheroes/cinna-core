import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useMutation } from "@tanstack/react-query"
import { useEffect } from "react"
import { z } from "zod"
import { CredentialsService } from "@/client"
import { Loader2 } from "lucide-react"

// Schema for query parameters
const searchSchema = z.object({
  code: z.string().optional(),
  state: z.string().optional(),
  error: z.string().optional(),
})

export const Route = createFileRoute("/credentials/oauth/callback")({
  component: OAuthCallback,
  validateSearch: searchSchema,
})

function OAuthCallback() {
  const navigate = useNavigate()
  const search = Route.useSearch()

  const callbackMutation = useMutation({
    mutationFn: (params: { code: string; state: string }) =>
      CredentialsService.oauthCallback({
        requestBody: {
          code: params.code,
          state: params.state,
        },
      }),
    onSuccess: (data) => {
      // Show success message via window.opener if in popup
      if (window.opener) {
        // Signal success to parent window
        try {
          window.opener.postMessage(
            { type: "oauth_success", credentialId: data.credential_id },
            window.location.origin
          )
        } catch (e) {
          console.error("Failed to post message to opener:", e)
        }
        // Close popup after short delay
        setTimeout(() => {
          window.close()
        }, 1000)
      } else {
        // Not in popup, redirect to credentials list
        navigate({ to: "/credentials" })
      }
    },
    onError: (error: Error) => {
      // Show error message via window.opener if in popup
      if (window.opener) {
        try {
          window.opener.postMessage(
            { type: "oauth_error", error: error.message },
            window.location.origin
          )
        } catch (e) {
          console.error("Failed to post message to opener:", e)
        }
        // Close popup after short delay
        setTimeout(() => {
          window.close()
        }, 2000)
      } else {
        // Not in popup, redirect to credentials list with error
        navigate({ to: "/credentials" })
      }
    },
  })

  useEffect(() => {
    // Check for OAuth error from Google
    if (search.error) {
      console.error("OAuth error from Google:", search.error)
      if (window.opener) {
        try {
          window.opener.postMessage(
            {
              type: "oauth_error",
              error: `Authorization failed: ${search.error}`,
            },
            window.location.origin
          )
        } catch (e) {
          console.error("Failed to post message to opener:", e)
        }
        setTimeout(() => {
          window.close()
        }, 2000)
      } else {
        navigate({ to: "/credentials" })
      }
      return
    }

    // Process OAuth callback if we have code and state
    if (search.code && search.state) {
      callbackMutation.mutate({
        code: search.code,
        state: search.state,
      })
    } else {
      // Missing required parameters
      console.error("Missing code or state parameter")
      if (window.opener) {
        try {
          window.opener.postMessage(
            {
              type: "oauth_error",
              error: "Missing authorization code or state parameter",
            },
            window.location.origin
          )
        } catch (e) {
          console.error("Failed to post message to opener:", e)
        }
        setTimeout(() => {
          window.close()
        }, 2000)
      } else {
        navigate({ to: "/credentials" })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center space-y-4">
        {callbackMutation.isPending && (
          <>
            <Loader2 className="h-8 w-8 animate-spin mx-auto" />
            <p className="text-lg font-medium">Completing authorization...</p>
            <p className="text-sm text-muted-foreground">
              Please wait while we connect your account
            </p>
          </>
        )}

        {callbackMutation.isSuccess && (
          <>
            <div className="h-8 w-8 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center mx-auto">
              <svg
                className="h-5 w-5 text-green-600 dark:text-green-200"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path d="M5 13l4 4L19 7"></path>
              </svg>
            </div>
            <p className="text-lg font-medium text-green-600 dark:text-green-200">
              Authorization successful!
            </p>
            <p className="text-sm text-muted-foreground">
              {window.opener
                ? "You can close this window now."
                : "Redirecting..."}
            </p>
          </>
        )}

        {callbackMutation.isError && (
          <>
            <div className="h-8 w-8 rounded-full bg-red-100 dark:bg-red-900 flex items-center justify-center mx-auto">
              <svg
                className="h-5 w-5 text-red-600 dark:text-red-200"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </div>
            <p className="text-lg font-medium text-red-600 dark:text-red-200">
              Authorization failed
            </p>
            <p className="text-sm text-muted-foreground">
              {callbackMutation.error?.message || "An error occurred"}
            </p>
            <p className="text-sm text-muted-foreground">
              {window.opener
                ? "You can close this window now."
                : "Redirecting..."}
            </p>
          </>
        )}

        {search.error && (
          <>
            <div className="h-8 w-8 rounded-full bg-red-100 dark:bg-red-900 flex items-center justify-center mx-auto">
              <svg
                className="h-5 w-5 text-red-600 dark:text-red-200"
                fill="none"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </div>
            <p className="text-lg font-medium text-red-600 dark:text-red-200">
              Authorization cancelled
            </p>
            <p className="text-sm text-muted-foreground">{search.error}</p>
            <p className="text-sm text-muted-foreground">
              {window.opener
                ? "You can close this window now."
                : "Redirecting..."}
            </p>
          </>
        )}
      </div>
    </div>
  )
}
