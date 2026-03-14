import type { RefObject } from "react"
import { Globe } from "lucide-react"
import { OpenAPI } from "@/client"

interface WebAppViewProps {
  agentId: string
  webappEnabled: boolean
  iframeRef?: RefObject<HTMLIFrameElement | null>
}

export function WebAppView({ agentId, webappEnabled, iframeRef }: WebAppViewProps) {
  if (!webappEnabled) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <Globe className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">
          Web App not enabled for this agent
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Enable it in agent settings
        </p>
      </div>
    )
  }

  const baseUrl = OpenAPI.BASE || ""
  const accessToken = localStorage.getItem("access_token") || ""
  const webappUrl = `${baseUrl}/api/v1/agents/${agentId}/webapp/?token=${encodeURIComponent(accessToken)}`

  return (
    <iframe
      ref={iframeRef}
      src={webappUrl}
      className="w-full h-full border-0"
      sandbox="allow-scripts allow-same-origin allow-forms"
      title="Agent Web App"
    />
  )
}
