import { X, File, FileText, Image, Archive } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { FileUploadPublic } from "@/client"

interface FileBadgeProps {
  file: FileUploadPublic
  onRemove?: () => void
  downloadable?: boolean
}

export function FileBadge({ file, onRemove, downloadable = false }: FileBadgeProps) {
  const getFileIcon = (mimeType: string) => {
    if (mimeType.startsWith('image/')) return <Image className="h-3 w-3" />
    if (mimeType.startsWith('text/')) return <FileText className="h-3 w-3" />
    if (mimeType.includes('zip') || mimeType.includes('tar')) return <Archive className="h-3 w-3" />
    return <File className="h-3 w-3" />
  }

  const truncateFilename = (name: string, maxLength: number = 20) => {
    if (name.length <= maxLength) return name
    const ext = name.split('.').pop()
    const base = name.substring(0, maxLength - (ext?.length || 0) - 4)
    return `${base}...${ext}`
  }

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const handleClick = async () => {
    if (downloadable) {
      // Download file with authentication
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const token = localStorage.getItem('access_token')

      try {
        const response = await fetch(`${apiUrl}/api/v1/files/${file.id}/download`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })

        if (!response.ok) {
          throw new Error('Download failed')
        }

        // Create blob and download
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = file.filename
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      } catch (error) {
        console.error('Failed to download file:', error)
      }
    }
  }

  return (
    <Badge
      variant="secondary"
      className={`flex items-center gap-1 pl-2 pr-1 ${downloadable ? 'cursor-pointer hover:bg-secondary/80' : ''}`}
      onClick={downloadable ? handleClick : undefined}
      title={`${file.filename} (${formatFileSize(file.file_size)})`}
    >
      {getFileIcon(file.mime_type)}
      <span className="text-xs">{truncateFilename(file.filename)}</span>
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="ml-1 hover:bg-background/50 rounded-full p-0.5"
          aria-label="Remove file"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </Badge>
  )
}
