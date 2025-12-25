import { FileText } from "lucide-react"

interface ReadToolBlockProps {
  filePath: string
}

export function ReadToolBlock({ filePath }: ReadToolBlockProps) {
  return (
    <div className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
      <FileText className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-blue-900 dark:text-blue-100">
          Reading file{" "}
          <code className="font-mono bg-blue-100 dark:bg-blue-900 px-1.5 py-0.5 rounded text-xs">
            {filePath}
          </code>
        </span>
      </div>
    </div>
  )
}
