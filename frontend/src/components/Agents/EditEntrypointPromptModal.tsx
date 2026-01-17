import { useEffect } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { AgentsService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from "@/components/ui/form"
import { Textarea } from "@/components/ui/textarea"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

const formSchema = z.object({
  entrypoint_prompt: z.string().optional(),
})

type FormData = z.infer<typeof formSchema>

interface EditEntrypointPromptModalProps {
  agentId: string
  currentPrompt: string | null | undefined
  open: boolean
  onClose: () => void
  readOnly?: boolean
}

export function EditEntrypointPromptModal({
  agentId,
  currentPrompt,
  open,
  onClose,
  readOnly = false,
}: EditEntrypointPromptModalProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      entrypoint_prompt: currentPrompt ?? "",
    },
  })

  useEffect(() => {
    if (open) {
      form.reset({
        entrypoint_prompt: currentPrompt ?? "",
      })
    }
  }, [open, currentPrompt, form])

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      AgentsService.updateAgent({ id: agentId, requestBody: data }),
    onSuccess: () => {
      showSuccessToast("Entrypoint prompt updated successfully")
      queryClient.invalidateQueries({ queryKey: ["agents"] })
      queryClient.invalidateQueries({ queryKey: ["agent", agentId] })
      onClose()
    },
    onError: handleError.bind(showErrorToast),
  })

  const onSubmit = (data: FormData) => {
    mutation.mutate(data)
  }

  const handleClose = () => {
    form.reset()
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {readOnly ? "View Entrypoint Prompt" : "Edit Entrypoint Prompt"}
          </DialogTitle>
          <DialogDescription>
            Simple, natural user question that triggers the agent (e.g.,
            "Summarize my unread emails.")
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="entrypoint_prompt"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Textarea
                      placeholder="Enter entrypoint prompt..."
                      className="min-h-[150px]"
                      {...field}
                      value={field.value || ""}
                      disabled={readOnly}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleClose}>
                {readOnly ? "Close" : "Cancel"}
              </Button>
              {!readOnly && (
                <LoadingButton
                  type="submit"
                  loading={mutation.isPending}
                  disabled={!form.formState.isDirty}
                >
                  Save
                </LoadingButton>
              )}
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
