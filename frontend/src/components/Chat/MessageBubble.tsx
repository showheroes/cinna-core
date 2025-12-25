import { formatDistanceToNow } from "date-fns"
import type { MessagePublic } from "@/client"
import ReactMarkdown from "react-markdown"
import { StreamEventRenderer } from "./StreamEventRenderer"

interface MessageBubbleProps {
  message: MessagePublic
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user"
  const isSystem = message.role === "system"

  if (isSystem) {
    return (
      <div className="flex justify-center my-4">
        <div className="bg-muted text-muted-foreground text-sm px-4 py-2 rounded-full max-w-md text-center">
          {message.content}
        </div>
      </div>
    )
  }

  // Extract metadata for display
  const model = message.message_metadata?.model
  const totalCost = message.message_metadata?.total_cost_usd
  const claudeVersion = message.message_metadata?.claude_code_version
  const streamingEvents = message.message_metadata?.streaming_events || []

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[70%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        }`}
      >
        <div className="space-y-2">
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <StreamEventRenderer events={streamingEvents} />
          )}
          <div className="flex items-center justify-between gap-2">
            <p
              className={`text-xs ${
                isUser ? "text-primary-foreground/70" : "text-muted-foreground"
              }`}
            >
              {formatDistanceToNow(new Date(message.timestamp), {
                addSuffix: true,
              })}
            </p>
            {!isUser && (model || totalCost || claudeVersion) && (
              <div
                className="text-xs text-muted-foreground/60 flex items-center gap-2"
                title={`Model: ${model || "unknown"}\n${totalCost ? `Cost: $${totalCost.toFixed(4)}` : ""}\n${claudeVersion ? `Claude Code: ${claudeVersion}` : ""}`}
              >
                {model && <span className="font-mono">{model.split('-').pop()}</span>}
                {totalCost && <span>${totalCost.toFixed(4)}</span>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
