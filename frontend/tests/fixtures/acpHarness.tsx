import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"
import { AcpConnectorsCard } from "@/components/Agents/Acp/AcpConnectorsCard"
import "@/index.css"

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})
// Inspect the real cache to prove one-time secrets leave no persisted UI state.
Object.assign(window, { acpQueryClient: queryClient })
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <div className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-2">
      <AcpConnectorsCard agentId="agent-1" />
    </div>
    <Toaster />
  </QueryClientProvider>,
)
