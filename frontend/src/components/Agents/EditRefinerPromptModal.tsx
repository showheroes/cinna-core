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
  refiner_prompt: z.string().optional(),
})

type FormData = z.infer<typeof formSchema>

interface EditRefinerPromptModalProps {
  agentId: string
  currentPrompt: string | null | undefined
  open: boolean
  onClose: () => void
  readOnly?: boolean
}

export function EditRefinerPromptModal({
  agentId,
  currentPrompt,
  open,
  onClose,
  readOnly = false,
}: EditRefinerPromptModalProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    defaultValues: {
      refiner_prompt: currentPrompt ?? "",
    },
  })

  useEffect(() => {
    if (open) {
      form.reset({
        refiner_prompt: currentPrompt ?? "",
      })
    }
  }, [open, currentPrompt, form])

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      AgentsService.updateAgent({ id: agentId, requestBody: data }),
    onSuccess: () => {
      showSuccessToast("Refiner prompt updated successfully")
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
      <DialogContent className="sm:max-w-5xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>
            {readOnly ? "View Refiner Prompt" : "Edit Refiner Prompt"}
          </DialogTitle>
          <DialogDescription>
            Instructions for refining task descriptions: default values,
            mandatory fields, and enhancement guidelines
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col flex-1 min-h-0"
          >
            <div className="flex-1 overflow-auto py-2">
              <FormField
                control={form.control}
                name="refiner_prompt"
                render={({ field }) => (
                  <FormItem className="h-full">
                    <FormControl>
                      <Textarea
                        placeholder="Enter refiner prompt..."
                        className="min-h-[500px] h-full resize-none"
                        {...field}
                        value={field.value || ""}
                        disabled={readOnly}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <DialogFooter className="pt-4 border-t mt-4">
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
