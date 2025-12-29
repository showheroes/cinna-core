import { FileText, FileJson, FileCode, ScrollText, Download, FileSpreadsheet, ChevronDown, ChevronRight, BookOpen, Folder, FolderOpen, Maximize2, Minimize2, Loader2, AlertCircle } from "lucide-react"
import { useState, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { WorkspaceService, OpenAPI } from "@/client"
import type { FileNode } from "@/client"
import type { AxiosRequestConfig } from "axios"

// Tree item types
interface FileItem {
  type: "file"
  name: string
  fileType: string // csv, json, txt, etc.
  size: string
  modified: string
}

interface FolderItem {
  type: "folder"
  name: string
  size: string
  modified: string
  children: TreeItem[]
}

type TreeItem = FileItem | FolderItem

// Stub data - will be replaced with API calls later
// Files now support nested folder structure
const STUB_FILES: TreeItem[] = [
  { type: "file", name: "employee_report_2025.csv", fileType: "csv", size: "2.3 MB", modified: "2025-12-29 10:30" },
  {
    type: "folder",
    name: "data",
    size: "2.8 MB",
    modified: "2025-12-29 10:28",
    children: [
      { type: "file", name: "customer_transactions_q4.json", fileType: "json", size: "456 KB", modified: "2025-12-29 10:28" },
      { type: "file", name: "sales_data_processed_dec.csv", fileType: "csv", size: "1.2 MB", modified: "2025-12-29 10:26" },
      {
        type: "folder",
        name: "archive",
        size: "1.1 MB",
        modified: "2025-12-29 10:20",
        children: [
          { type: "file", name: "legacy_customer_data_2024.json", fileType: "json", size: "234 KB", modified: "2025-12-29 09:15" },
          { type: "file", name: "vendor_bills_backup_nov_2024.csv", fileType: "csv", size: "890 KB", modified: "2025-12-29 09:10" },
        ],
      },
    ],
  },
  { type: "file", name: "processing_output_log.txt", fileType: "txt", size: "12 KB", modified: "2025-12-29 10:25" },
  {
    type: "folder",
    name: "reports",
    size: "1.8 MB",
    modified: "2025-12-29 10:20",
    children: [
      { type: "file", name: "quarterly_summary_metadata.json", fileType: "json", size: "8 KB", modified: "2025-12-29 10:20" },
      { type: "file", name: "vendor_bills_report_company_jan_2025.csv", fileType: "csv", size: "1.8 MB", modified: "2025-12-29 10:15" },
    ],
  },
]

const STUB_SCRIPTS: TreeItem[] = [
  { type: "file", name: "process_customer_data_pipeline.py", fileType: "py", size: "3.2 KB", modified: "2025-12-29 09:45" },
  {
    type: "folder",
    name: "utils",
    size: "3.6 KB",
    modified: "2025-12-29 09:30",
    children: [
      { type: "file", name: "data_validation_helpers.py", fileType: "py", size: "1.5 KB", modified: "2025-12-29 09:30" },
      { type: "file", name: "email_format_validators.py", fileType: "py", size: "2.1 KB", modified: "2025-12-29 09:25" },
    ],
  },
  { type: "file", name: "generate_quarterly_report_v2.py", fileType: "py", size: "5.8 KB", modified: "2025-12-29 09:30" },
]

const STUB_LOGS: TreeItem[] = [
  { type: "file", name: "agent_execution_main.log", fileType: "log", size: "124 KB", modified: "2025-12-29 10:35" },
  {
    type: "folder",
    name: "2025-12-29",
    size: "436 KB",
    modified: "2025-12-29 10:30",
    children: [
      { type: "file", name: "data_processing_pipeline.log", fileType: "log", size: "89 KB", modified: "2025-12-29 10:30" },
      { type: "file", name: "critical_errors_trace.log", fileType: "log", size: "2 KB", modified: "2025-12-29 10:25" },
      { type: "file", name: "debug_verbose_output.log", fileType: "log", size: "345 KB", modified: "2025-12-29 10:20" },
    ],
  },
  { type: "file", name: "system_health_monitor.log", fileType: "log", size: "67 KB", modified: "2025-12-29 10:15" },
]

const STUB_DOCS: TreeItem[] = [
  { type: "file", name: "project_overview_readme.md", fileType: "md", size: "8 KB", modified: "2025-12-29 09:00" },
  {
    type: "folder",
    name: "guides",
    size: "21 KB",
    modified: "2025-12-29 08:45",
    children: [
      { type: "file", name: "api_integration_guide_v3.md", fileType: "md", size: "15 KB", modified: "2025-12-29 08:45" },
      { type: "file", name: "initial_setup_instructions.md", fileType: "md", size: "6 KB", modified: "2025-12-29 08:30" },
    ],
  },
]

interface EnvironmentPanelProps {
  isOpen: boolean
  environmentId?: string
}

const getFileIcon = (fileType: string) => {
  switch (fileType) {
    case "csv":
      return <FileSpreadsheet className="h-4 w-4 text-green-500" />
    case "json":
      return <FileJson className="h-4 w-4 text-blue-500" />
    case "txt":
      return <FileText className="h-4 w-4 text-gray-500" />
    case "py":
      return <FileCode className="h-4 w-4 text-purple-500" />
    case "log":
      return <ScrollText className="h-4 w-4 text-yellow-500" />
    case "md":
      return <BookOpen className="h-4 w-4 text-indigo-500" />
    default:
      return <FileText className="h-4 w-4" />
  }
}

// Recursive tree item renderer component
interface TreeItemRendererProps {
  item: TreeItem
  level: number
  expandedFolders: Set<string>
  onToggleFolder: (path: string) => void
  onDownload: (fileName: string) => void
  path?: string
}

function TreeItemRenderer({ item, level, expandedFolders, onToggleFolder, onDownload, path = "" }: TreeItemRendererProps) {
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
          {getFileIcon(item.fileType)}
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

// Helper function to format file size
const formatFileSize = (bytes: number | null | undefined): string => {
  if (!bytes) return "0 B"
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${sizes[i]}`
}

// Helper function to format date
const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return ""
  const date = new Date(dateString)
  return date.toLocaleString("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  })
}

// Helper function to get file extension from name
const getFileExtension = (name: string): string => {
  const lastDot = name.lastIndexOf('.')
  return lastDot > 0 ? name.substring(lastDot + 1).toLowerCase() : 'txt'
}

// Convert API FileNode to UI TreeItem
const convertFileNodeToTreeItem = (node: FileNode): TreeItem => {
  if (node.type === "folder") {
    return {
      type: "folder",
      name: node.name,
      size: node.size ? formatFileSize(node.size) : "0 B",
      modified: formatDate(node.modified),
      children: node.children ? node.children.map(convertFileNodeToTreeItem) : []
    }
  } else {
    return {
      type: "file",
      name: node.name,
      fileType: getFileExtension(node.name),
      size: formatFileSize(node.size),
      modified: formatDate(node.modified)
    }
  }
}

export function EnvironmentPanel({ isOpen, environmentId }: EnvironmentPanelProps) {
  const [activeTab, setActiveTab] = useState("files")
  const [moreMenuOpen, setMoreMenuOpen] = useState(false)
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  const [isWidePanelMode, setIsWidePanelMode] = useState(false)

  // Set up request interceptor for blob downloads (only once)
  useEffect(() => {
    const interceptor = (config: AxiosRequestConfig) => {
      // If this is a download request, set responseType to blob
      if (config.url?.includes('/workspace/download/')) {
        config.responseType = 'blob'
      }
      return config
    }

    // Register interceptor
    OpenAPI.interceptors.request.use(interceptor)

    // Cleanup: remove interceptor when component unmounts
    return () => {
      OpenAPI.interceptors.request.eject(interceptor)
    }
  }, [])

  // Fetch workspace tree when panel is open and environmentId is available
  const {
    data: workspaceData,
    isLoading,
    error,
    refetch
  } = useQuery({
    queryKey: ["workspace-tree", environmentId],
    queryFn: () => WorkspaceService.getWorkspaceTree({ envId: environmentId! }),
    enabled: isOpen && !!environmentId,
    staleTime: 30000, // Cache for 30 seconds
  })

  if (!isOpen) return null

  const handleDownload = async (filePath: string) => {
    if (!environmentId) return

    try {
      // Use generated WorkspaceService client
      // The interceptor will set responseType: 'blob' for this request
      const blob = await WorkspaceService.downloadWorkspaceItem({
        envId: environmentId,
        path: filePath
      }) as unknown as Blob

      // Extract filename from path
      const filename = filePath.split('/').pop() || 'download'

      // Create blob URL and trigger download
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Download error:', error)
    }
  }

  const handleToggleFolder = (path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  const getMenuLabel = () => {
    if (activeTab === "files") return "Files"
    if (activeTab === "scripts") return "Scripts"
    if (activeTab === "logs") return "Logs"
    if (activeTab === "docs") return "Docs"
    return "Files"
  }

  const handleMenuItemClick = (value: string) => {
    setActiveTab(value)
    setMoreMenuOpen(false)
  }

  // Convert API data to TreeItem[] for each section
  const filesData: TreeItem[] = workspaceData?.files ? [convertFileNodeToTreeItem(workspaceData.files)] : []
  const scriptsData: TreeItem[] = workspaceData?.scripts ? [convertFileNodeToTreeItem(workspaceData.scripts)] : []
  const logsData: TreeItem[] = workspaceData?.logs ? [convertFileNodeToTreeItem(workspaceData.logs)] : []
  const docsData: TreeItem[] = workspaceData?.docs ? [convertFileNodeToTreeItem(workspaceData.docs)] : []

  // Render loading state
  const renderLoading = () => (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
      <Loader2 className="h-8 w-8 animate-spin" />
      <p className="text-sm">Loading workspace...</p>
    </div>
  )

  // Render error state
  const renderError = () => (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-4">
      <AlertCircle className="h-8 w-8 text-destructive" />
      <div className="text-center">
        <p className="text-sm font-medium mb-1">Failed to load workspace</p>
        <p className="text-xs">{error instanceof Error ? error.message : "Unknown error"}</p>
      </div>
      <Button size="sm" variant="outline" onClick={() => refetch()}>
        Retry
      </Button>
    </div>
  )

  // Render empty state
  const renderEmpty = () => (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-4">
      <FileText className="h-8 w-8" />
      <p className="text-sm text-center">No files found in this section</p>
    </div>
  )

  // Render no environment state
  const renderNoEnvironment = () => (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground px-4">
      <AlertCircle className="h-8 w-8" />
      <p className="text-sm text-center">No environment available for this session</p>
    </div>
  )

  return (
    <div className={`absolute top-0 right-0 h-full bg-background border-l border-border shadow-lg z-10 flex flex-col transition-all duration-200 ${isWidePanelMode ? 'w-[768px]' : 'w-96'}`}>
      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col flex-1 min-h-0">
        <div className="px-4 pt-3 pb-2 shrink-0 flex items-center gap-2">
          <div className="flex-1">
            <DropdownMenu open={moreMenuOpen} onOpenChange={setMoreMenuOpen}>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full justify-between"
                >
                  {getMenuLabel()}
                  <ChevronDown className="h-3 w-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className={isWidePanelMode ? "w-[720px]" : "w-[352px]"}>
                <DropdownMenuItem onClick={() => handleMenuItemClick("files")}>
                  <FileText className="h-4 w-4 mr-2" />
                  Files
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleMenuItemClick("scripts")}>
                  <FileCode className="h-4 w-4 mr-2" />
                  Scripts
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleMenuItemClick("logs")}>
                  <ScrollText className="h-4 w-4 mr-2" />
                  Logs
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => handleMenuItemClick("docs")}>
                  <BookOpen className="h-4 w-4 mr-2" />
                  Docs
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsWidePanelMode(!isWidePanelMode)}
            title={isWidePanelMode ? "Shrink panel" : "Expand panel"}
            className="shrink-0"
          >
            {isWidePanelMode ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </Button>
        </div>

        {/* Show loading/error/no-env state for all tabs */}
        {!environmentId ? (
          <div className="flex-1">{renderNoEnvironment()}</div>
        ) : isLoading ? (
          <div className="flex-1">{renderLoading()}</div>
        ) : error ? (
          <div className="flex-1">{renderError()}</div>
        ) : (
          <>
            {/* Files Tab */}
            <TabsContent value="files" className="flex-1 overflow-auto px-4 pb-4">
              {filesData[0]?.children && filesData[0].children.length > 0 ? (
                <div className="space-y-1">
                  {filesData[0].children.map((item, index) => (
                    <TreeItemRenderer
                      key={index}
                      item={item}
                      level={0}
                      expandedFolders={expandedFolders}
                      onToggleFolder={handleToggleFolder}
                      onDownload={handleDownload}
                      path="files"
                    />
                  ))}
                </div>
              ) : renderEmpty()}
            </TabsContent>

            {/* Scripts Tab */}
            <TabsContent value="scripts" className="flex-1 overflow-auto px-4 pb-4">
              {scriptsData[0]?.children && scriptsData[0].children.length > 0 ? (
                <div className="space-y-1">
                  {scriptsData[0].children.map((item, index) => (
                    <TreeItemRenderer
                      key={index}
                      item={item}
                      level={0}
                      expandedFolders={expandedFolders}
                      onToggleFolder={handleToggleFolder}
                      onDownload={handleDownload}
                      path="scripts"
                    />
                  ))}
                </div>
              ) : renderEmpty()}
            </TabsContent>

            {/* Logs Tab */}
            <TabsContent value="logs" className="flex-1 overflow-auto px-4 pb-4">
              {logsData[0]?.children && logsData[0].children.length > 0 ? (
                <div className="space-y-1">
                  {logsData[0].children.map((item, index) => (
                    <TreeItemRenderer
                      key={index}
                      item={item}
                      level={0}
                      expandedFolders={expandedFolders}
                      onToggleFolder={handleToggleFolder}
                      onDownload={handleDownload}
                      path="logs"
                    />
                  ))}
                </div>
              ) : renderEmpty()}
            </TabsContent>

            {/* Docs Tab */}
            <TabsContent value="docs" className="flex-1 overflow-auto px-4 pb-4">
              {docsData[0]?.children && docsData[0].children.length > 0 ? (
                <div className="space-y-1">
                  {docsData[0].children.map((item, index) => (
                    <TreeItemRenderer
                      key={index}
                      item={item}
                      level={0}
                      expandedFolders={expandedFolders}
                      onToggleFolder={handleToggleFolder}
                      onDownload={handleDownload}
                      path="docs"
                    />
                  ))}
                </div>
              ) : renderEmpty()}
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  )
}
