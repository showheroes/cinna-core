import ReactMarkdown from "react-markdown"
import { Loader2, Wrench } from "lucide-react"

interface StreamingMessageProps {
  content: string
}

export function StreamingMessage({ content }: StreamingMessageProps) {
  // Parse content to separate text from tool calls
  const parts = content.split(/\n---\n/)
  const hasMixedContent = parts.length > 1

  return (
    <div className="flex justify-start mb-4">
      <div className="max-w-[70%] rounded-lg px-4 py-3 bg-muted text-foreground">
        <div className="space-y-2">
          {content ? (
            hasMixedContent ? (
              // Has both text and tool calls
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
            ) : content.trim().startsWith("🔧 Using tool:") ? (
              // Pure tool call
              <div className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
                <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
                <pre className="text-blue-900 dark:text-blue-100 whitespace-pre-wrap font-sans text-xs">
                  {content.replace("🔧 ", "")}
                </pre>
              </div>
            ) : (
              // Pure text
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown>{content}</ReactMarkdown>
              </div>
            )
          ) : (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Thinking...</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-primary rounded-full animate-pulse" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 bg-primary rounded-full animate-pulse" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 bg-primary rounded-full animate-pulse" style={{ animationDelay: "300ms" }} />
            </div>
            <p className="text-xs text-muted-foreground">Streaming...</p>
          </div>
        </div>
      </div>
    </div>
  )
}
