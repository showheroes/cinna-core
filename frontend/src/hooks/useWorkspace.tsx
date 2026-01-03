import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  UserWorkspacesService,
  type UserWorkspaceCreate,
  type UserWorkspacePublic,
} from "@/client"
import { useState, useEffect, useRef, createContext, useContext, type ReactNode } from "react"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"
import { useRouter } from "@tanstack/react-router"

const WORKSPACE_STORAGE_KEY = "last_user_workspace_id"

const getActiveWorkspaceId = (): string | null => {
  return localStorage.getItem(WORKSPACE_STORAGE_KEY)
}

const setActiveWorkspaceId = (workspaceId: string | null) => {
  if (workspaceId === null) {
    localStorage.removeItem(WORKSPACE_STORAGE_KEY)
  } else {
    localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceId)
  }
}

// Create context for shared workspace state
const WorkspaceContext = createContext<{
  activeWorkspaceId: string | null
  setActiveWorkspaceIdState: (id: string | null) => void
} | null>(null)

export const WorkspaceProvider = ({ children }: { children: ReactNode }) => {
  const [activeWorkspaceId, setActiveWorkspaceIdState] = useState<string | null>(
    getActiveWorkspaceId()
  )

  return (
    <WorkspaceContext.Provider value={{ activeWorkspaceId, setActiveWorkspaceIdState }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

const useWorkspace = () => {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const router = useRouter()
  const context = useContext(WorkspaceContext)
  const isInitialMount = useRef(true)

  if (!context) {
    throw new Error('useWorkspace must be used within WorkspaceProvider')
  }

  const { activeWorkspaceId, setActiveWorkspaceIdState } = context

  // Load active workspace ID from localStorage on mount
  useEffect(() => {
    const storedId = getActiveWorkspaceId()
    setActiveWorkspaceIdState(storedId)
  }, [setActiveWorkspaceIdState])

  // Handle workspace change - redirect if needed
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }

    console.log('Workspace changed to:', activeWorkspaceId)

    // If on a detail page (not a list page), redirect to index
    const listPages = ['/', '/agents', '/credentials', '/sessions', '/activities']
    const currentPath = window.location.pathname

    if (!listPages.includes(currentPath)) {
      console.log('Redirecting to index from:', currentPath)
      router.navigate({ to: '/' })
    }

    // Note: We don't need to manually invalidate queries here
    // The key prop on components will force them to remount when activeWorkspaceId changes
    // React Query will automatically fetch when new queries are mounted
  }, [activeWorkspaceId, router])

  // Fetch all user workspaces
  const { data: workspacesData } = useQuery({
    queryKey: ["userWorkspaces"],
    queryFn: () => UserWorkspacesService.readWorkspaces(),
  })

  const workspaces = workspacesData?.data || []

  // Get the currently active workspace object
  const activeWorkspace: UserWorkspacePublic | "default" | null =
    activeWorkspaceId === null
      ? "default"
      : workspaces.find((w) => w.id === activeWorkspaceId) || null

  // Switch to a different workspace
  const switchWorkspace = (workspaceId: string | null) => {
    setActiveWorkspaceId(workspaceId)
    setActiveWorkspaceIdState(workspaceId)
  }

  // Create new workspace
  const createWorkspaceMutation = useMutation({
    mutationFn: (data: UserWorkspaceCreate) =>
      UserWorkspacesService.createWorkspace({ requestBody: data }),
    onSuccess: (newWorkspace) => {
      queryClient.invalidateQueries({ queryKey: ["userWorkspaces"] })
      // Automatically switch to the newly created workspace
      switchWorkspace(newWorkspace.id)
    },
    onError: handleError.bind(showErrorToast),
  })

  // Delete workspace
  const deleteWorkspaceMutation = useMutation({
    mutationFn: (workspaceId: string) =>
      UserWorkspacesService.deleteWorkspace({ workspaceId }),
    onSuccess: (_, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ["userWorkspaces"] })
      // If deleted workspace was active, switch to default
      if (activeWorkspaceId === deletedId) {
        switchWorkspace(null)
      }
    },
    onError: handleError.bind(showErrorToast),
  })

  // Update workspace
  const updateWorkspaceMutation = useMutation({
    mutationFn: ({
      workspaceId,
      data,
    }: {
      workspaceId: string
      data: { name: string }
    }) =>
      UserWorkspacesService.updateWorkspace({
        workspaceId,
        requestBody: data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userWorkspaces"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  return {
    workspaces,
    activeWorkspace,
    activeWorkspaceId,
    switchWorkspace,
    createWorkspaceMutation,
    deleteWorkspaceMutation,
    updateWorkspaceMutation,
  }
}

export { getActiveWorkspaceId, setActiveWorkspaceId }
export default useWorkspace
