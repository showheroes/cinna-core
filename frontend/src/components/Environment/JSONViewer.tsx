import { useState, useEffect, useCallback, useMemo } from "react"
import { ChevronDown, ChevronRight, UnfoldVertical, FoldVertical } from "lucide-react"
import { Button } from "@/components/ui/button"

interface JSONViewerProps {
  content: string
}

interface JSONNodeProps {
  name: string | null
  value: unknown
  depth: number
  defaultExpanded: boolean
  generation: number
  isLast: boolean
}

function JSONNode({ name, value, depth, defaultExpanded, generation, isLast }: JSONNodeProps) {
  const [expanded, setExpanded] = useState(() => defaultExpanded || depth < 2)

  useEffect(() => {
    setExpanded(defaultExpanded || depth < 2)
  }, [generation])

  const toggle = useCallback(() => setExpanded((prev) => !prev), [])

  const comma = isLast ? "" : ","
  const paddingLeft = `${depth * 20}px`

  const renderKey = name !== null ? (
    <span className="text-slate-700 dark:text-slate-300">{`"${name}": `}</span>
  ) : null

  // Primitive values
  if (value === null) {
    return (
      <div className="leading-6" style={{ paddingLeft }}>
        {renderKey}
        <span className="text-red-400 dark:text-red-500">null</span>
        {comma}
      </div>
    )
  }

  if (typeof value === "string") {
    return (
      <div className="leading-6 break-all" style={{ paddingLeft }}>
        {renderKey}
        <span className="text-green-600 dark:text-green-400">"{value}"</span>
        {comma}
      </div>
    )
  }

  if (typeof value === "number") {
    return (
      <div className="leading-6" style={{ paddingLeft }}>
        {renderKey}
        <span className="text-orange-500 dark:text-orange-400">{String(value)}</span>
        {comma}
      </div>
    )
  }

  if (typeof value === "boolean") {
    return (
      <div className="leading-6" style={{ paddingLeft }}>
        {renderKey}
        <span className="text-purple-600 dark:text-purple-400">{String(value)}</span>
        {comma}
      </div>
    )
  }

  // Arrays
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <div className="leading-6" style={{ paddingLeft }}>
          {renderKey}
          <span className="text-slate-500 dark:text-slate-400">[]</span>
          {comma}
        </div>
      )
    }

    return (
      <>
        <div
          className="leading-6 cursor-pointer hover:bg-muted/50 rounded select-none"
          style={{ paddingLeft }}
          onClick={toggle}
        >
          {expanded ? (
            <ChevronDown className="inline h-3.5 w-3.5 text-muted-foreground mr-1 -mt-0.5" />
          ) : (
            <ChevronRight className="inline h-3.5 w-3.5 text-muted-foreground mr-1 -mt-0.5" />
          )}
          {renderKey}
          <span className="text-slate-500 dark:text-slate-400">[</span>
          {!expanded && (
            <>
              <span className="text-slate-400 dark:text-slate-500 italic text-xs ml-1">
                {value.length} {value.length === 1 ? "item" : "items"}
              </span>
              <span className="text-slate-500 dark:text-slate-400">]</span>
              {comma}
            </>
          )}
        </div>
        {expanded && (
          <>
            {value.map((item, index) => (
              <JSONNode
                key={index}
                name={null}
                value={item}
                depth={depth + 1}
                defaultExpanded={defaultExpanded}
                generation={generation}
                isLast={index === value.length - 1}
              />
            ))}
            <div className="leading-6" style={{ paddingLeft }}>
              <span className="text-slate-500 dark:text-slate-400">]</span>
              {comma}
            </div>
          </>
        )}
      </>
    )
  }

  // Objects
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)

    if (entries.length === 0) {
      return (
        <div className="leading-6" style={{ paddingLeft }}>
          {renderKey}
          <span className="text-slate-500 dark:text-slate-400">{"{}"}</span>
          {comma}
        </div>
      )
    }

    return (
      <>
        <div
          className="leading-6 cursor-pointer hover:bg-muted/50 rounded select-none"
          style={{ paddingLeft }}
          onClick={toggle}
        >
          {expanded ? (
            <ChevronDown className="inline h-3.5 w-3.5 text-muted-foreground mr-1 -mt-0.5" />
          ) : (
            <ChevronRight className="inline h-3.5 w-3.5 text-muted-foreground mr-1 -mt-0.5" />
          )}
          {renderKey}
          <span className="text-slate-500 dark:text-slate-400">{"{"}</span>
          {!expanded && (
            <>
              <span className="text-slate-400 dark:text-slate-500 italic text-xs ml-1">
                {entries.length} {entries.length === 1 ? "key" : "keys"}
              </span>
              <span className="text-slate-500 dark:text-slate-400">{"}"}</span>
              {comma}
            </>
          )}
        </div>
        {expanded && (
          <>
            {entries.map(([key, val], index) => (
              <JSONNode
                key={key}
                name={key}
                value={val}
                depth={depth + 1}
                defaultExpanded={defaultExpanded}
                generation={generation}
                isLast={index === entries.length - 1}
              />
            ))}
            <div className="leading-6" style={{ paddingLeft }}>
              <span className="text-slate-500 dark:text-slate-400">{"}"}</span>
              {comma}
            </div>
          </>
        )}
      </>
    )
  }

  // Fallback for unexpected types
  return (
    <div className="leading-6" style={{ paddingLeft }}>
      {renderKey}
      <span className="text-slate-500">{String(value)}</span>
      {comma}
    </div>
  )
}

export function JSONViewer({ content }: JSONViewerProps) {
  const [defaultExpanded, setDefaultExpanded] = useState(false)
  const [generation, setGeneration] = useState(0)

  const parsed = useMemo(() => {
    try {
      // content may already be parsed by the HTTP client if the server returned JSON content-type
      if (typeof content !== "string") {
        return { data: content, error: null }
      }
      return { data: JSON.parse(content), error: null }
    } catch (e) {
      return { data: null, error: (e as Error).message }
    }
  }, [content])

  const handleExpandAll = useCallback(() => {
    setDefaultExpanded(true)
    setGeneration((g) => g + 1)
  }, [])

  const handleCollapseAll = useCallback(() => {
    setDefaultExpanded(false)
    setGeneration((g) => g + 1)
  }, [])

  if (parsed.error) {
    return (
      <div className="h-full flex flex-col overflow-auto">
        <div className="bg-destructive/10 text-destructive text-sm px-4 py-2 border-b border-destructive/20">
          Failed to parse JSON: {parsed.error}
        </div>
        <pre className="p-6 font-mono text-sm whitespace-pre-wrap break-all">
          {typeof content === "string" ? content : JSON.stringify(content, null, 2)}
        </pre>
      </div>
    )
  }

  if (typeof content === "string" && !content.trim()) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">Empty file</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-auto">
      <div className="flex items-center gap-1 px-4 py-2 border-b bg-muted/30">
        <Button variant="ghost" size="sm" onClick={handleExpandAll} className="h-7 text-xs gap-1">
          <UnfoldVertical className="h-3.5 w-3.5" />
          Expand All
        </Button>
        <Button variant="ghost" size="sm" onClick={handleCollapseAll} className="h-7 text-xs gap-1">
          <FoldVertical className="h-3.5 w-3.5" />
          Collapse All
        </Button>
      </div>
      <div className="p-4 font-mono text-sm">
        <JSONNode
          name={null}
          value={parsed.data}
          depth={0}
          defaultExpanded={defaultExpanded}
          generation={generation}
          isLast={true}
        />
      </div>
    </div>
  )
}
