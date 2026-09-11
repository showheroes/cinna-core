import { Monitor } from "lucide-react"

import type { InputTaskPublic } from "@/client"
import { RowFlag } from "@/components/Common/ListRow"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { getTaskExternalExecution } from "@/utils/taskExternalExecutor"

interface TaskExternalExecutorProps {
  task: Pick<InputTaskPublic, "external_executor" | "status">
}

export function TaskExternalExecutorFlag({ task }: TaskExternalExecutorProps) {
  const execution = getTaskExternalExecution(task)
  if (!execution) return null

  return <RowFlag icon={Monitor} label={`${execution.label}. ${execution.reason}`} />
}

export function TaskExternalExecutorNotice({ task }: TaskExternalExecutorProps) {
  const execution = getTaskExternalExecution(task)
  if (!execution) return null

  return (
    <Alert role="status">
      <Monitor />
      <AlertTitle>{execution.label}</AlertTitle>
      <AlertDescription className="break-words">
        {execution.reason}
      </AlertDescription>
    </Alert>
  )
}
