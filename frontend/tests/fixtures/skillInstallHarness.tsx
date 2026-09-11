import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import {
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from "@tanstack/react-router"
import { useState } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"

import { AddSkillToAgentDialog } from "@/components/Catalog/AddSkillToAgentDialog"
import "@/index.css"

// Only the production dialog and its providers. The browser tests intercept
// every API call; no application login, database or environment is involved.
function InstallDialogHost() {
  const [open, setOpen] = useState(true)
  return open ? (
    <AddSkillToAgentDialog
      packageId="package-1"
      packageName="ERP"
      open
      onOpenChange={setOpen}
    />
  ) : (
    <p>Install dialog closed</p>
  )
}

const rootRoute = createRootRoute({
  component: () => (
    <>
      <Outlet />
      <Toaster />
    </>
  ),
})
const installRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: InstallDialogHost,
})
const agentRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/agent/$agentId",
  component: () => <p>Agent credentials</p>,
})
const router = createRouter({
  routeTree: rootRoute.addChildren([installRoute, agentRoute]),
})
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <RouterProvider router={router} />
  </QueryClientProvider>,
)
