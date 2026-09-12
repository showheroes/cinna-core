import type { ServerChannelPublic } from "@/client"

const CAPABILITY_FACTS = [
  ["supports_threads", "Thread replies"],
  ["supports_message_fetch", "Quoted messages"],
  ["supports_thread_history", "Thread history"],
] as const

export function ChannelConversationCapabilities({
  channel,
}: {
  channel: ServerChannelPublic | null
}) {
  const capabilities = channel?.conversation_capabilities
  if (!channel) {
    return (
      <p className="text-xs text-muted-foreground">
        Save the channel to check which conversation features its credentials
        support.
      </p>
    )
  }
  if (!capabilities || Object.keys(capabilities).length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        Capability information is unavailable. Reopen this form to check again.
      </p>
    )
  }

  const readAccessUnavailable =
    capabilities.supports_message_fetch === false ||
    capabilities.supports_thread_history === false

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">
        Capabilities reflect the saved credentials. Save credential changes to
        refresh them.
      </p>
      <dl className="space-y-1 text-xs">
        {CAPABILITY_FACTS.map(([key, label]) => (
          <div key={key} className="flex items-start justify-between gap-4">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words text-right">
              {capabilities[key] === true
                ? key === "supports_threads"
                  ? "Available in threaded spaces"
                  : "Available"
                : capabilities[key] === false
                  ? "Unavailable"
                  : "Unknown"}
            </dd>
          </div>
        ))}
      </dl>
      {readAccessUnavailable && (
        <p className="break-words text-xs text-warning">
          Read access could not be verified. Follow this channel's Setup
          instructions to configure the read scope, re-authorize an existing
          app, and ensure the app is a member of the space. Questions still
          reach the agent when earlier context is unavailable.
        </p>
      )}
    </div>
  )
}
