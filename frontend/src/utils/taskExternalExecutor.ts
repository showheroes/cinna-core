import type { InputTaskPublic } from "@/client"

type ExecutionTask = Pick<InputTaskPublic, "external_executor" | "status">

/** Keep execution ownership wording identical in task lists and controls. */
export function getTaskExternalExecution(task: ExecutionTask | undefined) {
  if (task?.external_executor == null) return null

  const isDesktop = task.external_executor.toLowerCase() === "desktop"
  const isRunning = ["in_progress", "running"].includes(task.status)
  const client = isDesktop ? "Desktop" : "an external client"

  return {
    label: isDesktop
      ? isRunning ? "Running on Desktop" : "Managed by Desktop"
      : isRunning ? "Running externally" : "Managed externally",
    reason: `Execution and refinement are managed by ${client}. Release this task in that client before running it here.`,
  }
}
