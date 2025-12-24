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
