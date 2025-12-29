import { ChevronDown, ChevronRight, Folder, FolderOpen, Download } from "lucide-react"
import { FileIcon } from "./FileIcon"
import type { TreeItem } from "./types"

interface TreeItemRendererProps {
  item: TreeItem
  level: number
  expandedFolders: Set<string>
  onToggleFolder: (path: string) => void
  onDownload: (fileName: string) => void
  path?: string
}

export function TreeItemRenderer({
  item,
  level,
  expandedFolders,
  onToggleFolder,
  onDownload,
  path = ""
}: TreeItemRendererProps) {
  const currentPath = path ? `${path}/${item.name}` : item.name
  const isExpanded = expandedFolders.has(currentPath)
  const paddingLeft = `${level * 12}px`

  if (item.type === "folder") {
    return (
      <>
        <div
          className="flex items-center justify-between py-1 px-2 rounded-md hover:bg-muted/50 group transition-colors cursor-pointer"
          style={{ paddingLeft }}
        >
          <div className="flex items-center gap-2 min-w-0 flex-1" onClick={() => onToggleFolder(currentPath)}>
            {isExpanded ? (
              <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
            ) : (
              <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
            )}
            {isExpanded ? (
              <FolderOpen className="h-4 w-4 text-blue-400 shrink-0" title={item.modified} />
            ) : (
              <Folder className="h-4 w-4 text-blue-400 shrink-0" title={item.modified} />
            )}
            <p className="text-sm font-medium truncate" title={item.name}>{item.name}</p>
            <span className="text-xs text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-auto mr-2">
              {item.size}
            </span>
          </div>
          <button
            className="opacity-0 group-hover:opacity-100 shrink-0 p-0 hover:text-foreground text-muted-foreground transition-colors ml-1"
            onClick={(e) => {
              e.stopPropagation()
              onDownload(currentPath)
            }}
            title="Download folder"
          >
            <Download className="h-4 w-4" />
          </button>
        </div>
        {isExpanded && item.children.map((child, index) => (
          <TreeItemRenderer
            key={index}
            item={child}
            level={level + 1}
            expandedFolders={expandedFolders}
            onToggleFolder={onToggleFolder}
            onDownload={onDownload}
            path={currentPath}
          />
        ))}
      </>
    )
  }

  // File item
  const lastDotIndex = item.name.lastIndexOf('.')
  const baseName = lastDotIndex > 0 ? item.name.substring(0, lastDotIndex) : item.name
  const extension = lastDotIndex > 0 ? item.name.substring(lastDotIndex) : ''

  return (
    <div
      className="flex items-center justify-between py-1 px-2 rounded-md hover:bg-muted/50 group transition-colors"
      style={{ paddingLeft: `${level * 12 + 24}px` }} // Extra padding for files to align with folder content
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <div className="shrink-0" title={item.modified}>
          <FileIcon fileType={item.fileType} />
        </div>
        <p className="text-sm font-medium truncate" title={item.name}>
          {baseName}<span className="text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity">{extension}</span>
        </p>
        <span className="text-xs text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-auto">
          {item.size}
        </span>
        <button
          className="opacity-0 group-hover:opacity-100 shrink-0 p-0 hover:text-foreground text-muted-foreground transition-colors"
          onClick={() => onDownload(currentPath)}
          title="Download"
        >
          <Download className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
