import type { PluginSyncResponse } from "@/client"

/** A persisted plugin link may still have failed to reach an environment. */
export function hasPluginSyncIssues(
  result: Pick<
    PluginSyncResponse,
    "failed_syncs" | "unsupported_syncs" | "partial_failures"
  >,
): boolean {
  return (
    (result.failed_syncs ?? 0) > 0 ||
    (result.unsupported_syncs ?? 0) > 0 ||
    !!result.partial_failures
  )
}

/** Used when navigation leaves no host for the environment issues dialog. */
export function pluginInstallSyncWarning(name: string): string {
  return `${name} installed, but it didn't reach every environment — check the agent's Addons tab`
}
