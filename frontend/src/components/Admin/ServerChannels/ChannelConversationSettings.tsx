import { useFormContext } from "react-hook-form"

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"

export interface ConversationSettingsValues {
  reply_here_phrase: string
  thread_backfill_enabled: boolean
}

/** Both controls are drafts committed by the channel form's Save button. */
export function ChannelConversationSettings({
  disabled,
}: {
  disabled: boolean
}) {
  const { control } = useFormContext<ConversationSettingsValues>()

  return (
    <div className="space-y-4">
      <FormField
        control={control}
        name="reply_here_phrase"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Reply-here phrase</FormLabel>
            <FormControl>
              <Input {...field} maxLength={64} disabled={disabled} />
            </FormControl>
            <FormDescription>
              End a message with this phrase to request a reply in the group
              conversation. It is removed from the question. In direct messages,
              it does not change where the reply goes.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={control}
        name="thread_backfill_enabled"
        render={({ field }) => (
          <FormItem className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <FormLabel>Read thread history</FormLabel>
              <FormDescription>
                Include earlier messages and attachments when the agent is
                mentioned in an existing thread. This may include messages from
                people outside this channel's sender allowlist. Requires read
                access and app membership in the space.
              </FormDescription>
            </div>
            <FormControl>
              <Switch
                checked={field.value}
                onCheckedChange={field.onChange}
                disabled={disabled}
              />
            </FormControl>
          </FormItem>
        )}
      />
    </div>
  )
}
