import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  GuestShareService,
  SessionsService,
  MessagesService,
} from "@/client"
import type { SessionPublicExtended } from "@/client"
import { GuestShareProvider } from "@/hooks/useGuestShare"
import { MessageList } from "@/components/Chat/MessageList"
import { MessageInput } from "@/components/Chat/MessageInput"
import { useSessionStreaming } from "@/hooks/useSessionStreaming"
import { Button } from "@/components/ui/button"
import {
  MessageSquarePlus,
  MessageCircle,
  Loader2,
  AlertCircle,
  Clock,
  Bot,
  Package,
} from "lucide-react"
import { EnvironmentPanel } from "@/components/Environment/EnvironmentPanel"

export const Route = createFileRoute("/guest/$guestShareToken")({
  component: GuestChatPage,
  validateSearch: (search: Record<string, unknown>) => ({
    sessionId: (search.sessionId as string) || undefined,
  }),
  head: () => ({
    meta: [
      {
        title: "Guest Chat",
      },
    ],
  }),
})

// ── Types for untyped backend responses ─────────────────────────────────

interface GuestShareInfoResponse {
  agent_name: string | null
  agent_description: string | null
  is_valid: boolean
  guest_share_id: string | null
}

interface GuestShareAuthResponse {
  access_token: string
  token_type: string
  guest_share_id: string
  agent_id: string
}

interface GuestShareActivateResponse {
  guest_share_id: string
  agent_id: string
  agent_name: string
}

// ── Helpers ──────────────────────────────────────────────────────────────

/**
 * Decode a JWT payload without verification and return guest claims
 * if it's a guest share token. Returns null for regular user JWTs.
 */
function parseGuestJwt(
  token: string
): { sub: string; agent_id: string; exp: number } | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]))
    if (payload.role === "chat-guest" && payload.token_type === "guest_share") {
      return { sub: payload.sub, agent_id: payload.agent_id, exp: payload.exp }
    }
  } catch {
    // Malformed token — treat as not a guest JWT
  }
  return null
}

// ── Main Component ──────────────────────────────────────────────────────

function GuestChatPage() {
  const { guestShareToken } = Route.useParams()
  const { sessionId: selectedSessionId } = Route.useSearch()
  const navigate = useNavigate()

  // Auth flow state
  const [authState, setAuthState] = useState<
    "loading" | "authenticating" | "ready" | "error"
  >("loading")
  const [errorMessage, setErrorMessage] = useState<string>("")
  const [guestShareId, setGuestShareId] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)
  const [agentName, setAgentName] = useState<string>("")
  const [agentDescription, setAgentDescription] = useState<string | null>(null)

  // Session state
  const [envPanelOpen, setEnvPanelOpen] = useState(false)

  const selectSession = useCallback(
    (id: string) => {
      navigate({
        to: "/guest/$guestShareToken",
        params: { guestShareToken },
        search: { sessionId: id },
        replace: true,
      })
    },
    [navigate, guestShareToken]
  )

  const authAttempted = useRef(false)
  const messageInputRef = useRef<HTMLTextAreaElement>(null)

  // Step 1: Fetch share info (no auth required)
  const {
    data: shareInfo,
    isLoading: infoLoading,
    error: infoError,
  } = useQuery({
    queryKey: ["guestShareInfo", guestShareToken],
    queryFn: async () => {
      const result = await GuestShareService.guestShareInfo({
        token: guestShareToken,
      })
      return result as unknown as GuestShareInfoResponse
    },
    retry: false,
  })

  // Step 2: Auth flow after share info is loaded
  useEffect(() => {
    if (authAttempted.current) return
    if (infoLoading || infoError) return
    if (!shareInfo) return

    if (!shareInfo.is_valid) {
      setAuthState("error")
      setErrorMessage(
        shareInfo.guest_share_id
          ? "This guest share link has expired. Contact the owner for a new link."
          : "This guest share link is invalid or has been removed."
      )
      return
    }

    setAgentName(shareInfo.agent_name || "Agent")
    setAgentDescription(shareInfo.agent_description || null)
    authAttempted.current = true
    setAuthState("authenticating")

    const authenticate = async () => {
      try {
        const existingToken = localStorage.getItem("access_token")

        if (existingToken) {
          // Check if the stored token is a guest JWT (from a previous anonymous visit)
          const guestClaims = parseGuestJwt(existingToken)

          if (guestClaims) {
            // Already have a guest JWT — reuse if still valid, otherwise re-auth
            if (guestClaims.exp * 1000 > Date.now()) {
              setGuestShareId(guestClaims.sub)
              setAgentId(guestClaims.agent_id)
              setAuthState("ready")
              return
            }
            // Guest JWT expired — clear and get a fresh one
            localStorage.removeItem("access_token")
            await authenticateAnonymous()
          } else {
            // Regular user JWT — call activate to create a grant
            try {
              const activateResult = (await GuestShareService.guestShareActivate({
                token: guestShareToken,
              })) as unknown as GuestShareActivateResponse

              setGuestShareId(activateResult.guest_share_id)
              setAgentId(activateResult.agent_id)
              setAgentName(activateResult.agent_name || shareInfo.agent_name || "Agent")
              setAuthState("ready")
            } catch (activateError: any) {
              // If activation fails (e.g. stale JWT), fall back to anonymous auth
              if ([401, 403, 404].includes(activateError?.status)) {
                localStorage.removeItem("access_token")
                await authenticateAnonymous()
              } else {
                throw activateError
              }
            }
          }
        } else {
          await authenticateAnonymous()
        }
      } catch (error: any) {
        console.error("Guest auth failed:", error)
        setAuthState("error")
        if (error?.status === 410) {
          setErrorMessage(
            "This guest share link has expired. Contact the owner for a new link."
          )
        } else if (error?.status === 404) {
          setErrorMessage("This guest share link is invalid or has been removed.")
        } else {
          setErrorMessage("Something went wrong. Please try again.")
        }
      }
    }

    const authenticateAnonymous = async () => {
      const authResult = (await GuestShareService.guestShareAuthenticate({
        token: guestShareToken,
      })) as unknown as GuestShareAuthResponse

      localStorage.setItem("access_token", authResult.access_token)
      setGuestShareId(authResult.guest_share_id)
      setAgentId(authResult.agent_id)
      setAuthState("ready")
    }

    authenticate()
  }, [shareInfo, infoLoading, infoError, guestShareToken])

  // Handle info loading error
  useEffect(() => {
    if (infoError) {
      setAuthState("error")
      setErrorMessage("Something went wrong. Please try again.")
    }
  }, [infoError])

  // Render based on auth state
  if (authState === "loading" || authState === "authenticating") {
    return (
      <GuestLoadingScreen
        agentName={agentName || "the agent"}
        isAuthenticating={authState === "authenticating"}
      />
    )
  }

  if (authState === "error") {
    return <GuestErrorScreen message={errorMessage} />
  }

  return (
    <GuestShareProvider
      guestShareId={guestShareId}
      agentId={agentId}
      guestShareToken={guestShareToken}
    >
      <div className="flex flex-col h-screen bg-background">
        {/* Header */}
        <GuestChatHeader
          agentName={agentName}
          agentDescription={agentDescription}
          envPanelOpen={envPanelOpen}
          onToggleEnvPanel={() => setEnvPanelOpen(!envPanelOpen)}
          hasSession={selectedSessionId !== undefined}
        />

        {/* Content area */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar */}
          <GuestSessionSidebar
            guestShareId={guestShareId!}
            agentId={agentId!}
            selectedSessionId={selectedSessionId ?? null}
            onSelectSession={selectSession}
          />

          {/* Main chat area */}
          <div className="flex-1 flex flex-col min-h-0 min-w-0 relative">
            {selectedSessionId ? (
              <GuestChatArea
                sessionId={selectedSessionId}
                agentId={agentId}
                messageInputRef={messageInputRef}
                envPanelOpen={envPanelOpen}
              />
            ) : (
              <GuestEmptyState
                agentName={agentName}
                agentId={agentId!}
                guestShareId={guestShareId!}
                onSessionCreated={selectSession}
              />
            )}
          </div>
        </div>
      </div>
    </GuestShareProvider>
  )
}

// ── Loading Screen ──────────────────────────────────────────────────────

function GuestLoadingScreen({
  agentName,
  isAuthenticating,
}: {
  agentName: string
  isAuthenticating: boolean
}) {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-background">
      <div className="flex flex-col items-center gap-4">
        <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
          <Bot className="h-8 w-8 text-primary" />
        </div>
        <div className="flex items-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <p className="text-muted-foreground">
            {isAuthenticating
              ? `Connecting to ${agentName}...`
              : "Loading..."}
          </p>
        </div>
      </div>
    </div>
  )
}

// ── Error Screen ────────────────────────────────────────────────────────

function GuestErrorScreen({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-background">
      <div className="flex flex-col items-center gap-4 max-w-md text-center px-4">
        <div className="h-16 w-16 rounded-full bg-destructive/10 flex items-center justify-center">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h1 className="text-xl font-semibold">Unable to access</h1>
        <p className="text-muted-foreground">{message}</p>
      </div>
    </div>
  )
}

// ── Header ──────────────────────────────────────────────────────────────

function GuestChatHeader({
  agentName,
  agentDescription,
  envPanelOpen,
  onToggleEnvPanel,
  hasSession,
}: {
  agentName: string
  agentDescription: string | null
  envPanelOpen: boolean
  onToggleEnvPanel: () => void
  hasSession: boolean
}) {
  return (
    <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-4 border-b px-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex items-center gap-3 min-w-0 flex-1">
        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <Bot className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold truncate">{agentName}</h1>
          <p className="text-xs text-muted-foreground truncate">
            {agentDescription || "Guest Session"}
          </p>
        </div>
      </div>
      {hasSession && (
        <Button
          variant={envPanelOpen ? "secondary" : "ghost"}
          size="sm"
          onClick={onToggleEnvPanel}
          className="shrink-0"
        >
          <Package className="h-4 w-4 mr-1.5" />
          App
        </Button>
      )}
    </header>
  )
}

// ── Session Sidebar ─────────────────────────────────────────────────────

function GuestSessionSidebar({
  guestShareId,
  agentId,
  selectedSessionId,
  onSelectSession,
}: {
  guestShareId: string
  agentId: string
  selectedSessionId: string | null
  onSelectSession: (id: string) => void
}) {
  const queryClient = useQueryClient()

  const {
    data: sessionsData,
    isLoading: sessionsLoading,
  } = useQuery({
    queryKey: ["guestSessions", guestShareId],
    queryFn: () =>
      SessionsService.listSessions({
        guestShareId,
        orderBy: "last_message_at",
        orderDesc: true,
        limit: 100,
      }),
    refetchInterval: 10000,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      SessionsService.createSession({
        requestBody: {
          agent_id: agentId,
          mode: "conversation",
          guest_share_id: guestShareId,
        },
      }),
    onSuccess: (session) => {
      onSelectSession(session.id)
      queryClient.invalidateQueries({ queryKey: ["guestSessions", guestShareId] })
    },
  })

  const sessions = sessionsData?.data || []

  return (
    <div className="w-64 border-r bg-muted/30 flex flex-col shrink-0 hidden md:flex">
      {/* New Session button */}
      <div className="p-3 border-b">
        <Button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          variant="outline"
          size="sm"
          className="w-full gap-2"
        >
          {createMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <MessageSquarePlus className="h-4 w-4" />
          )}
          New Session
        </Button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {sessionsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <p className="text-xs text-muted-foreground">No sessions yet</p>
          </div>
        ) : (
          <div className="py-1">
            {sessions.map((session: SessionPublicExtended) => (
              <button
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className={`w-full text-left px-3 py-2 text-sm transition-colors hover:bg-accent ${
                  selectedSessionId === session.id
                    ? "bg-accent"
                    : ""
                }`}
              >
                <div className="flex items-start gap-2">
                  <MessageCircle className="h-3.5 w-3.5 text-blue-500 shrink-0 mt-0.5" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">
                      {session.title || `Session`}
                    </p>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                      <Clock className="h-3 w-3" />
                      <span>
                        {new Date(
                          session.last_message_at || session.created_at
                        ).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Empty State ─────────────────────────────────────────────────────────

function GuestEmptyState({
  agentName,
  agentId,
  guestShareId,
  onSessionCreated,
}: {
  agentName: string
  agentId: string
  guestShareId: string
  onSessionCreated: (id: string) => void
}) {
  const queryClient = useQueryClient()

  const createMutation = useMutation({
    mutationFn: () =>
      SessionsService.createSession({
        requestBody: {
          agent_id: agentId,
          mode: "conversation",
          guest_share_id: guestShareId,
        },
      }),
    onSuccess: (session) => {
      onSessionCreated(session.id)
      queryClient.invalidateQueries({ queryKey: ["guestSessions", guestShareId] })
    },
  })

  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-4">
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
          <Bot className="h-8 w-8 text-primary" />
        </div>
        <h2 className="text-lg font-semibold">Start a conversation</h2>
        <p className="text-muted-foreground text-sm max-w-sm">
          Begin chatting with {agentName}. Your conversations will be saved and you
          can continue them later.
        </p>
      </div>
      <Button
        onClick={() => createMutation.mutate()}
        disabled={createMutation.isPending}
        size="lg"
        className="gap-2"
      >
        {createMutation.isPending ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <MessageSquarePlus className="h-5 w-5" />
        )}
        New Session
      </Button>
    </div>
  )
}

// ── Chat Area ───────────────────────────────────────────────────────────

function GuestChatArea({
  sessionId,
  agentId,
  messageInputRef,
  envPanelOpen,
}: {
  sessionId: string
  agentId: string | null
  messageInputRef: React.RefObject<HTMLTextAreaElement | null>
  envPanelOpen: boolean
}) {
  const [isSessionStreaming, setIsSessionStreaming] = useState(false)

  const {
    data: session,
    isLoading: sessionLoading,
  } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => SessionsService.getSession({ id: sessionId }),
    enabled: !!sessionId,
    refetchInterval: isSessionStreaming ? 3000 : 10000,
  })

  // Derive streaming state from session
  useEffect(() => {
    const streaming =
      session?.interaction_status === "running" ||
      session?.interaction_status === "pending_stream"
    setIsSessionStreaming(streaming)
  }, [session?.interaction_status])

  const {
    data: messagesData,
    isLoading: messagesLoading,
  } = useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () =>
      MessagesService.getMessages({ sessionId, offset: 0, limit: 100 }),
    enabled: !!sessionId,
    refetchInterval: isSessionStreaming ? 2000 : undefined,
  })

  const {
    sendMessage,
    stopMessage,
    isStreaming,
    streamingEvents,
    isInterruptPending,
  } = useSessionStreaming({
    sessionId,
    session: session
      ? { interaction_status: session.interaction_status, mode: session.mode }
      : null,
    messagesData: messagesData
      ? { data: messagesData.data as any }
      : null,
    onError: (error) => {
      console.error("Guest message error:", error)
    },
  })

  const handleSendMessage = useCallback(
    async (content: string, fileIds?: string[]) => {
      await sendMessage(content, undefined, fileIds)
    },
    [sendMessage]
  )

  const handleSendAnswer = useCallback(
    async (content: string, answersToMessageId: string) => {
      await sendMessage(content, answersToMessageId)
    },
    [sendMessage]
  )

  const handleSendSimpleMessage = useCallback(
    async (content: string) => {
      await sendMessage(content)
    },
    [sendMessage]
  )

  // Auto-focus input when loaded
  useEffect(() => {
    if (!sessionLoading && !messagesLoading && messageInputRef.current) {
      messageInputRef.current.focus()
    }
  }, [sessionLoading, messagesLoading, messageInputRef])

  if (sessionLoading || messagesLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!session) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-muted-foreground">Session not found</p>
      </div>
    )
  }

  const messages = messagesData?.data || []

  return (
    <>
      <div className="flex flex-col flex-1 min-h-0 relative">
        <MessageList
          messages={messages}
          isLoading={messagesLoading}
          streamingEvents={streamingEvents}
          isStreaming={isStreaming}
          onSendAnswer={handleSendAnswer}
          onSendMessage={handleSendSimpleMessage}
          conversationModeUi="detailed"
          agentId={agentId ?? undefined}
          sessionId={sessionId}
        />
        <EnvironmentPanel
          isOpen={envPanelOpen}
          environmentId={session.environment_id}
          agentId={agentId ?? undefined}
        />
      </div>
      <MessageInput
        ref={messageInputRef}
        onSend={handleSendMessage}
        onStop={stopMessage}
        sendDisabled={isStreaming}
        isInterruptPending={isInterruptPending}
        placeholder={
          isStreaming ? "Agent is responding..." : "Type your message..."
        }
        agentId={agentId ?? undefined}
        mode="conversation"
      />
    </>
  )
}
