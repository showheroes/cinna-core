import { formatDistanceToNow } from "date-fns"
import type { MessagePublic } from "@/client"
import ReactMarkdown from "react-markdown"
import { Wrench } from "lucide-react"

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

  // Parse content to separate text from tool calls
  const parts = !isUser && !isSystem ? message.content.split(/\n---\n/) : [message.content]
  const hasMixedContent = parts.length > 1

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
          ) : hasMixedContent ? (
            // Agent message with both text and tool calls
            <div className="space-y-3">
              {parts.map((part, idx) => {
                if (part.trim().startsWith("🔧 Using tool:")) {
                  // Tool call section
                  return (
                    <div key={idx} className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
                      <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                      <pre className="text-blue-900 dark:text-blue-100 whitespace-pre-wrap font-sans text-xs">
                        {part.replace("🔧 ", "")}
                      </pre>
                    </div>
                  )
                } else if (part.trim()) {
                  // Regular text section
                  return (
                    <div key={idx} className="prose prose-sm dark:prose-invert max-w-none">
                      <ReactMarkdown>{part}</ReactMarkdown>
                    </div>
                  )
                }
                return null
              })}
            </div>
          ) : message.content.trim().startsWith("🔧 Using tool:") ? (
            // Pure tool call
            <div className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
              <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
              <pre className="text-blue-900 dark:text-blue-100 whitespace-pre-wrap font-sans text-xs">
                {message.content.replace("🔧 ", "")}
              </pre>
            </div>
          ) : (
            // Pure text
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
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
