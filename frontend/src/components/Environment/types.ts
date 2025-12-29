// Tree item types
export interface FileItem {
  type: "file"
  name: string
  fileType: string // csv, json, txt, etc.
  size: string
  modified: string
}

export interface FolderItem {
  type: "folder"
  name: string
  size: string
  modified: string
  children: TreeItem[]
}

export type TreeItem = FileItem | FolderItem
