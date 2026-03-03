# Frontend Development - LLM Quick Reference

## Toast Notifications
- **USE**: `useCustomToast` hook from `@/hooks/useCustomToast`
- **DO NOT USE**: `@/hooks/use-toast` (does not exist)
- Library: `sonner` (not shadcn/ui toast)
```tsx
import useCustomToast from "@/hooks/useCustomToast"
const { showSuccessToast, showErrorToast } = useCustomToast()
showSuccessToast("Success message")
showErrorToast("Error message")
```

## API Client
- **NEVER manually edit** files in `src/client/`
- Auto-generated from backend OpenAPI spec
- Regenerate after backend changes: `bash scripts/generate-client.sh`
- Import services: `import { UsersService, AgentsService } from "@/client"`

## TanStack Query Patterns
```tsx
// Query
const { data } = useQuery({
  queryKey: ["key"],
  queryFn: () => ServiceName.methodName(),
})

// Mutation
const mutation = useMutation({
  mutationFn: (data) => ServiceName.create({ requestBody: data }),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["key"] })
    showSuccessToast("Success")
  },
  onError: () => showErrorToast("Error"),
})
```

## Routing
- File-based routing in `src/routes/`
- Protected routes: `src/routes/_layout/` directory
- Route guard pattern:
```tsx
export const Route = createFileRoute("/_layout/path")({
  component: Component,
  beforeLoad: async () => {
    if (!isLoggedIn()) throw redirect({ to: "/login" })
  },
})
```

## Auth
- Hook: `useAuth()` from `@/hooks/useAuth`
- Returns: `{ user, loginMutation, logoutMutation }`
- Access token stored in localStorage: `access_token`
- Check login: `isLoggedIn()` utility function

## Component Libraries
- UI: shadcn/ui components from `@/components/ui/`
- Forms: `react-hook-form` + `zod` validation
- Icons: lucide-react

## State Management
- **Primary**: TanStack Query (no Redux/Zustand)
- **Auth state**: Managed by TanStack Query with `["currentUser"]` key
- **Local state**: React useState

## Common Patterns
- User settings components: `src/components/UserSettings/`
- Settings page uses Tabs component with config array
- Always invalidate queries after mutations
- Use `queryClient.invalidateQueries()` for cache updates

## Environment Variables
- Accessed via `import.meta.env.VITE_*`
- API URL: `import.meta.env.VITE_API_URL`

## Styling
- Tailwind CSS
- Theme: Light/dark mode support via shadcn/ui
- Use `className` prop with Tailwind utilities
- Dynamic classes: Use template literals with full class names (Tailwind JIT)
```tsx
const colorPreset = getColorPreset(agent.ui_color_preset)
<div className={`rounded-lg p-3 ${colorPreset.iconBg}`}>
```

## Dialog/Modal Pattern
```tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

const [isOpen, setIsOpen] = useState(false)

<Dialog open={isOpen} onOpenChange={setIsOpen}>
  <DialogContent className="sm:max-w-md">
    <DialogHeader>
      <DialogTitle>Title</DialogTitle>
      <DialogDescription>Description</DialogDescription>
    </DialogHeader>
    {/* Content */}
  </DialogContent>
</Dialog>
```

## Utilities Pattern
- Shared constants/helpers: `src/utils/` directory
- Export types and functions
- Example: `src/utils/colorPresets.ts` for color configuration
```tsx
export type ColorPreset = "slate" | "blue" | ...
export const getColorPreset = (preset: string | null | undefined) => { ... }
```

## Tab Components
- Use `HashTabs` component for tabbed interfaces
- Location: `@/components/Common/HashTabs`
```tsx
const tabs = [
  { value: "tab1", title: "Tab 1", content: <Component1 /> },
  { value: "tab2", title: "Tab 2", content: <Component2 /> },
]
<HashTabs tabs={tabs} defaultTab="tab1" />
```

## Workspace Management

### State Access
- **Hook**: `useWorkspace()` from `@/hooks/useWorkspace`
- **Returns**: `{ activeWorkspaceId, activeWorkspace, switchWorkspace, workspaces, ... }`
- **Important**: Uses React Context - all components share same workspace state

### List Pages with Workspace Filtering
**Problem**: When user switches workspaces, list pages must refresh with new data.

**Solution**: React `key` prop pattern + Context for state sharing

**Implementation Pattern**:
```tsx
function MyListPage() {
  const { activeWorkspaceId } = useWorkspace()

  // Query key MUST include activeWorkspaceId
  const { data } = useQuery({
    queryKey: ["myEntities", activeWorkspaceId],
    queryFn: async ({ queryKey }) => {
      const [, workspaceId] = queryKey  // Read from queryKey, not closure
      return MyService.list({
        userWorkspaceId: workspaceId ?? "",  // Empty string = default workspace
      })
    },
  })

  // Key prop forces remount when workspace changes
  return (
    <div key={activeWorkspaceId ?? 'default'}>
      {/* Component content */}
    </div>
  )
}
```

**Why This Pattern**:
- **React Context**: Ensures all components see workspace state changes (prevents desync)
- **Key prop**: Forces component unmount/remount when workspace changes → fresh queries
- **Query key includes workspace**: Separates cache by workspace
- **Read from queryKey param**: Avoids closure issues with stale workspace values
- **Empty string convention**: Backend interprets `""` as default workspace filter

**Required for pages**: `/`, `/agents`, `/credentials`, `/sessions`, `/activities`

### Detail Pages with Workspace Context
**Problem**: When viewing an entity detail page (e.g., agent page) and switching workspaces, that entity likely doesn't exist in the new workspace.

**Solution**: Automatic redirect to index

**Implementation**: Handled in `useWorkspace` hook automatically - detail pages redirect to `/` on workspace switch

**List of workspace-aware pages**:
- `/` - index/dashboard
- `/agents` - agents list
- `/credentials` - credentials list
- `/sessions` - sessions list
- `/activities` - activities list

**All other pages**: Auto-redirect to index on workspace switch

### Creating Entities in Active Workspace
```tsx
const { activeWorkspaceId } = useWorkspace()

const createMutation = useMutation({
  mutationFn: (data) => MyService.create({
    requestBody: {
      ...data,
      user_workspace_id: activeWorkspaceId,  // Assign to active workspace
    }
  }),
})
```
