import { FileEdit, ChevronDown, ChevronUp } from "lucide-react"
import { useState, useMemo } from "react"

interface WriteToolBlockProps {
  filePath: string
  content: string
}

const MAX_PREVIEW_LINES = 5

export function WriteToolBlock({ filePath, content }: WriteToolBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const { previewContent, hasMore, totalLines } = useMemo(() => {
    const lines = content.split('\n')
    const totalLines = lines.length
    const hasMore = totalLines > MAX_PREVIEW_LINES
    const previewContent = hasMore && !isExpanded
      ? lines.slice(0, MAX_PREVIEW_LINES).join('\n')
      : content

    return { previewContent, hasMore, totalLines }
  }, [content, isExpanded])

  return (
    <div className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
      <FileEdit className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="text-blue-900 dark:text-blue-100 mb-2">
          Writing file{" "}
          <code className="font-mono bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded text-xs">
            {filePath}
          </code>
        </div>

        <div className="bg-white dark:bg-gray-900 border border-blue-200 dark:border-blue-700 rounded p-2">
          <pre className="text-xs text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre-wrap break-words font-mono">
            {previewContent}
          </pre>

          {hasMore && (
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-2 flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 transition-colors"
            >
              {isExpanded ? (
                <>
                  <ChevronUp className="h-3 w-3" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" />
                  Show all ({totalLines} lines)
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
