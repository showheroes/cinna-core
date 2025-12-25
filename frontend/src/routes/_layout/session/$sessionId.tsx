import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect } from "react"
import { ArrowLeft } from "lucide-react"

import { SessionsService, MessagesService } from "@/client"
import { MessageList } from "@/components/Chat/MessageList"
import { MessageInput } from "@/components/Chat/MessageInput"
import { Button } from "@/components/ui/button"
import PendingItems from "@/components/Pending/PendingItems"
import useCustomToast from "@/hooks/useCustomToast"
import { useMessageStream } from "@/hooks/useMessageStream"
import { usePageHeader } from "@/routes/_layout"

export const Route = createFileRoute("/_layout/session/$sessionId")({
  component: ChatInterface,
})

function ChatInterface() {
  const { sessionId } = Route.useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { setHeaderContent } = usePageHeader()

  const {
    data: session,
    isLoading: sessionLoading,
    error: sessionError,
  } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => SessionsService.getSession({ id: sessionId }),
    enabled: !!sessionId,
    refetchInterval: 10000, // Poll for status updates every 10s
  })

  const {
    data: messagesData,
    isLoading: messagesLoading,
  } = useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => MessagesService.getMessages({ sessionId, offset: 0, limit: 100 }),
    enabled: !!sessionId,
  })

  const switchModeMutation = useMutation({
    mutationFn: (newMode: string) =>
      SessionsService.switchSessionMode({ id: sessionId, newMode }),
    onSuccess: (updatedSession) => {
      showSuccessToast(`Switched to ${updatedSession.mode} mode`)
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to switch mode")
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
    },
  })

  const { sendMessage, isStreaming, streamingEvents } = useMessageStream({
    sessionId,
    onSuccess: () => {
      // Messages are already refreshed by the hook
    },
    onError: (error) => {
      showErrorToast(error.message || "Failed to send message")
    },
  })

  const handleModeSwitch = () => {
    if (!session) return
    const newMode = session.mode === "building" ? "conversation" : "building"
    switchModeMutation.mutate(newMode)
  }

  const handleSendMessage = async (content: string) => {
    await sendMessage(content)
  }

  const handleBack = () => {
    navigate({ to: "/sessions" })
  }

  // Update header when session loads
  useEffect(() => {
    if (session) {
      const isBuilding = session.mode === "building"
      setHeaderContent(
        <>
          <div className="flex items-center gap-3 min-w-0">
            <Button variant="ghost" size="sm" onClick={handleBack} className="shrink-0">
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="min-w-0">
              <h1 className="text-base font-semibold truncate">
                {session.title || "Untitled Session"}
              </h1>
              <p className="text-xs text-muted-foreground">
                <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
                  isBuilding ? "bg-orange-500" : "bg-blue-500"
                }`} />
                {isBuilding ? "Building Mode" : "Conversation Mode"}
              </p>
            </div>
          </div>
          <Button
            variant={isBuilding ? "outline" : "default"}
            size="sm"
            onClick={handleModeSwitch}
            className={`gap-2 shrink-0 ${
              isBuilding
                ? "border-orange-500 text-orange-700 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-950/20"
                : "bg-blue-500 hover:bg-blue-600 text-white"
            }`}
          >
            Switch Mode
          </Button>
        </>
      )
    }
    return () => setHeaderContent(null)
  }, [session, setHeaderContent])

  if (sessionLoading || messagesLoading) {
    return <PendingItems />
  }

  if (sessionError || !session) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive mb-4">Error loading session</p>
        <button onClick={handleBack} className="text-primary hover:underline">
          Back to sessions
        </button>
      </div>
    )
  }

  const messages = messagesData?.data || []

  // Check if session is in error state
  if (session.status === "error") {
    return (
      <div className="flex flex-col h-full min-h-0">
        <div className="flex-1 flex items-center justify-center min-h-0">
          <div className="text-center space-y-4">
            <p className="text-destructive font-semibold">Session encountered an error</p>
            <p className="text-muted-foreground">
              Please check the environment status or create a new session.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const isDisabled = isStreaming || session.status !== "active"

  return (
    <div className="flex flex-col h-full min-h-0">
      <MessageList
        messages={messages}
        isLoading={messagesLoading}
        streamingEvents={streamingEvents}
        isStreaming={isStreaming}
      />
      <MessageInput
        onSend={handleSendMessage}
        disabled={isDisabled}
        placeholder={
          isStreaming
            ? "Agent is responding..."
            : session.status !== "active"
            ? "Session is not active"
            : "Type your message..."
        }
      />
    </div>
  )
}
