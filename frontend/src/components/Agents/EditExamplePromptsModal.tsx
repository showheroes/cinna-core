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
  promptsText: z.string().optional(),
})

type FormData = z.infer<typeof formSchema>

interface EditExamplePromptsModalProps {
  agentId: string
  currentPrompts: string[] | null | undefined
  open: boolean
  onClose: () => void
  readOnly?: boolean
}

export function EditExamplePromptsModal({
  agentId,
  currentPrompts,
  open,
  onClose,
  readOnly = false,
}: EditExamplePromptsModalProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const promptsToText = (prompts: string[] | null | undefined): string =>
    (prompts ?? []).join("\n")

  const textToPrompts = (text: string): string[] =>
    text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0)

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      promptsText: promptsToText(currentPrompts),
    },
  })

  useEffect(() => {
    if (open) {
      form.reset({
        promptsText: promptsToText(currentPrompts),
      })
    }
  }, [open, currentPrompts, form])

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      AgentsService.updateAgent({
        id: agentId,
        requestBody: {
          example_prompts: textToPrompts(data.promptsText ?? ""),
        },
      }),
    onSuccess: () => {
      showSuccessToast("Example prompts updated successfully")
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
            {readOnly ? "View Example Prompts" : "Edit Example Prompts"}
          </DialogTitle>
          <DialogDescription>
            Define example prompts for MCP clients. One per line in the format:{" "}
            <code>slug: prompt text</code>
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="promptsText"
              render={({ field }) => (
                <FormItem>
                  <FormControl>
                    <Textarea
                      placeholder={`report_status: Send me status report for the current month\ncheck_email: Check my email for urgent items`}
                      className="min-h-[150px] font-mono text-sm"
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
