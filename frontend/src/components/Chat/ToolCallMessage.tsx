import { Wrench, ChevronDown, ChevronUp } from "lucide-react"
import { useState } from "react"

interface ToolCallMessageProps {
  toolName: string
  toolInput?: Record<string, any>
  timestamp?: string
}

export function ToolCallMessage({ toolName, toolInput, timestamp }: ToolCallMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="flex justify-center my-3">
      <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg px-4 py-2 max-w-[80%]">
        <div className="flex items-center gap-2">
          <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          <span className="text-sm font-medium text-blue-900 dark:text-blue-100">
            Using tool: <code className="font-mono bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded">{toolName}</code>
          </span>
          {toolInput && Object.keys(toolInput).length > 0 && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="ml-auto text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200"
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </button>
          )}
        </div>
        {isExpanded && toolInput && (
          <div className="mt-2 pt-2 border-t border-blue-200 dark:border-blue-800">
            <pre className="text-xs text-blue-800 dark:text-blue-200 overflow-x-auto">
              {JSON.stringify(toolInput, null, 2)}
            </pre>
          </div>
        )}
        {timestamp && (
          <div className="text-xs text-blue-600 dark:text-blue-400 mt-1">
            {timestamp}
          </div>
        )}
      </div>
    </div>
  )
}
