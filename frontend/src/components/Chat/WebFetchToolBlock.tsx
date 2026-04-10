import { Globe } from "lucide-react"

interface WebFetchToolBlockProps {
  url: string
  prompt?: string
}

export function WebFetchToolBlock({ url, prompt }: WebFetchToolBlockProps) {
  return (
    <div className="flex items-start gap-2 text-sm bg-slate-100 dark:bg-slate-800 border border-border rounded px-3 py-2">
      <Globe className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-foreground/90">
          Fetching{" "}
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="font-mono bg-slate-200 dark:bg-slate-700 px-1.5 py-0.5 rounded text-xs hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors underline decoration-dotted underline-offset-2 cursor-pointer"
          >
            {url}
          </a>
        </span>
        {prompt && (
          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{prompt}</p>
        )}
      </div>
    </div>
  )
}
