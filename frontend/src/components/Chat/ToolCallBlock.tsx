import { Wrench } from "lucide-react"
import { MarkdownRenderer } from "./MarkdownRenderer"

interface ToolCallBlockProps {
  toolName: string
  toolInput?: Record<string, any>
}

export function ToolCallBlock({ toolName, toolInput }: ToolCallBlockProps) {
  return (
    <div className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
      <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="font-medium text-blue-900 dark:text-blue-100 mb-1">
          Using tool: <code className="font-mono bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded text-xs">{toolName}</code>
        </div>
        {toolInput && Object.keys(toolInput).length > 0 && (
          <div className="space-y-1 text-xs">
            {Object.entries(toolInput).map(([key, value]) => (
              <div key={key} className="flex flex-col gap-0.5">
                <span className="font-semibold text-blue-700 dark:text-blue-300">{key}:</span>
                <div className="pl-3 text-blue-800 dark:text-blue-200">
                  {typeof value === 'string' ? (
                    // Check if the value contains markdown-like content (code blocks, lists, etc.)
                    value.includes('\n') || value.includes('```') || value.includes('- ') ? (
                      <MarkdownRenderer
                        content={value}
                        className="prose prose-xs dark:prose-invert max-w-none"
                      />
                    ) : (
                      <span className="whitespace-pre-wrap break-words">{value}</span>
                    )
                  ) : (
                    <pre className="whitespace-pre-wrap break-words font-mono">
                      {JSON.stringify(value, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
