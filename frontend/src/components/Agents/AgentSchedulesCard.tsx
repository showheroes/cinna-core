import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CalendarClock,
  Plus,
  Trash2,
  Pencil,
  Sparkles,
  Check,
  Clock,
  AlertCircle,
  Power,
  PowerOff,
} from "lucide-react"
import { useState } from "react"

import { AgentsService } from "@/client"
import type { AgentSchedulePublic } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface AgentSchedulesCardProps {
  agentId: string
}

function formatNextExecution(isoDate?: string | null): string {
  if (!isoDate) return "Unknown"
  try {
    let utcDateString = isoDate
    if (
      !isoDate.endsWith("Z") &&
      !isoDate.includes("+") &&
      isoDate.includes("T")
    ) {
      utcDateString = isoDate + "Z"
    }
    const date = new Date(utcDateString)
    return date.toLocaleString(undefined, {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    })
  } catch {
    return isoDate
  }
}

export function AgentSchedulesCard({ agentId }: AgentSchedulesCardProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone

  // Create dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createName, setCreateName] = useState("")
  const [createInput, setCreateInput] = useState("")
  const [createPrompt, setCreatePrompt] = useState("")
  const [createGenerated, setCreateGenerated] = useState<{
    description: string
    cron_string: string
    next_execution: string
  } | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<AgentSchedulePublic | null>(null)
  const [editName, setEditName] = useState("")
  const [editInput, setEditInput] = useState("")
  const [editPrompt, setEditPrompt] = useState("")
  const [editGenerated, setEditGenerated] = useState<{
    description: string
    cron_string: string
    next_execution: string
  } | null>(null)
  const [editError, setEditError] = useState<string | null>(null)

  const queryKey = ["agent-schedules", agentId]

  // Fetch schedules
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => AgentsService.listSchedules({ id: agentId }),
    enabled: !!agentId,
  })

  const schedules = data?.data ?? []

  // Generate mutation (stateless AI)
  const generateMutation = useMutation({
    mutationFn: (naturalLanguage: string) =>
      AgentsService.generateSchedule({
        id: agentId,
        requestBody: { natural_language: naturalLanguage, timezone: userTimezone },
      }),
  })

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (body: {
      name: string
      cron_string: string
      timezone: string
      description: string
      prompt?: string | null
      enabled: boolean
    }) =>
      AgentsService.createSchedule({ id: agentId, requestBody: body }),
    onSuccess: () => {
      showSuccessToast("Schedule created")
      queryClient.invalidateQueries({ queryKey })
      handleCreateDialogClose(false)
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to create schedule")
    },
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({
      scheduleId,
      body,
    }: {
      scheduleId: string
      body: Record<string, any>
    }) =>
      AgentsService.updateSchedule({
        id: agentId,
        scheduleId,
        requestBody: body,
      }),
    onSuccess: () => {
      showSuccessToast("Schedule updated")
      queryClient.invalidateQueries({ queryKey })
      setEditDialogOpen(false)
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to update schedule")
    },
  })

  // Toggle mutation
  const toggleMutation = useMutation({
    mutationFn: ({
      scheduleId,
      enabled,
    }: {
      scheduleId: string
      enabled: boolean
    }) =>
      AgentsService.updateSchedule({
        id: agentId,
        scheduleId,
        requestBody: { enabled },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to toggle schedule")
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (scheduleId: string) =>
      AgentsService.deleteSchedule({ id: agentId, scheduleId }),
    onSuccess: () => {
      showSuccessToast("Schedule deleted")
      queryClient.invalidateQueries({ queryKey })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to delete schedule")
    },
  })

  // Create dialog handlers
  const handleCreateDialogClose = (open: boolean) => {
    setCreateDialogOpen(open)
    if (!open) {
      setCreateName("")
      setCreateInput("")
      setCreatePrompt("")
      setCreateGenerated(null)
      setCreateError(null)
    }
  }

  const handleCreateGenerate = async () => {
    if (!createInput.trim()) return
    setCreateError(null)
    setCreateGenerated(null)
    try {
      const result = await generateMutation.mutateAsync(createInput)
      if (result.success && result.cron_string && result.description) {
        setCreateGenerated({
          description: result.description,
          cron_string: result.cron_string,
          next_execution: result.next_execution ?? "",
        })
      } else {
        setCreateError(result.error || "Failed to generate schedule")
      }
    } catch (error: any) {
      setCreateError(error.message || "Failed to generate schedule")
    }
  }

  const handleCreate = () => {
    if (!createName.trim() || !createGenerated) return
    createMutation.mutate({
      name: createName,
      cron_string: createGenerated.cron_string,
      timezone: userTimezone,
      description: createGenerated.description,
      prompt: createPrompt.trim() || null,
      enabled: true,
    })
  }

  // Edit dialog handlers
  const handleEditOpen = (schedule: AgentSchedulePublic) => {
    setEditingSchedule(schedule)
    setEditName(schedule.name)
    setEditInput("")
    setEditPrompt(schedule.prompt ?? "")
    setEditGenerated(null)
    setEditError(null)
    setEditDialogOpen(true)
  }

  const handleEditGenerate = async () => {
    if (!editInput.trim()) return
    setEditError(null)
    setEditGenerated(null)
    try {
      const result = await generateMutation.mutateAsync(editInput)
      if (result.success && result.cron_string && result.description) {
        setEditGenerated({
          description: result.description,
          cron_string: result.cron_string,
          next_execution: result.next_execution ?? "",
        })
      } else {
        setEditError(result.error || "Failed to generate schedule")
      }
    } catch (error: any) {
      setEditError(error.message || "Failed to generate schedule")
    }
  }

  const handleEditSave = () => {
    if (!editingSchedule) return
    const body: Record<string, any> = {}

    if (editName !== editingSchedule.name) body.name = editName
    if (editPrompt !== (editingSchedule.prompt ?? "")) {
      body.prompt = editPrompt.trim() || null
    }
    if (editGenerated) {
      body.cron_string = editGenerated.cron_string
      body.timezone = userTimezone
      body.description = editGenerated.description
    }

    updateMutation.mutate({ scheduleId: editingSchedule.id, body })
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <CalendarClock className="h-5 w-5" />
              Schedules
            </CardTitle>
            <CardDescription>
              Schedule execution times for this agent with different prompts and cadences
            </CardDescription>
          </div>
          <Dialog open={createDialogOpen} onOpenChange={handleCreateDialogClose}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1" />
                New
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Schedule</DialogTitle>
                <DialogDescription>
                  Add a new execution schedule for this agent.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="schedule-name">Name</Label>
                  <Input
                    id="schedule-name"
                    placeholder="e.g., Daily data collection"
                    value={createName}
                    onChange={(e) => setCreateName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Timing</Label>
                  <div className="flex gap-2">
                    <Input
                      value={createInput}
                      onChange={(e) => setCreateInput(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleCreateGenerate()}
                      placeholder="e.g., every workday at 7am"
                      disabled={generateMutation.isPending}
                    />
                    <Button
                      onClick={handleCreateGenerate}
                      disabled={!createInput.trim() || generateMutation.isPending}
                      variant="outline"
                    >
                      {generateMutation.isPending ? (
                        "..."
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4 mr-1" />
                          Generate
                        </>
                      )}
                    </Button>
                  </div>
                  {createGenerated && (
                    <div className="bg-secondary p-3 rounded-md space-y-1.5">
                      <div className="flex items-start gap-2">
                        <Check className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                        <span className="font-medium text-sm">
                          {createGenerated.description}
                        </span>
                      </div>
                      {createGenerated.next_execution && (
                        <div className="flex items-start gap-2 text-sm text-muted-foreground">
                          <Clock className="h-4 w-4 mt-0.5 shrink-0" />
                          <span>
                            Next: {formatNextExecution(createGenerated.next_execution)}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                  {createError && (
                    <div className="bg-destructive/10 border border-destructive/20 p-3 rounded-md">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                        <span className="text-sm text-destructive">
                          {createError}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="schedule-prompt">Prompt (optional)</Label>
                  <Textarea
                    id="schedule-prompt"
                    placeholder="Leave empty to use agent's entrypoint prompt"
                    value={createPrompt}
                    onChange={(e) => setCreatePrompt(e.target.value)}
                    rows={3}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  onClick={handleCreate}
                  disabled={
                    !createName.trim() ||
                    !createGenerated ||
                    createMutation.isPending
                  }
                >
                  {createMutation.isPending ? "Creating..." : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : schedules.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No schedules yet. Create one to automate this agent.
          </p>
        ) : (
          <div className="space-y-1.5">
            {schedules.map((schedule) => (
              <div
                key={schedule.id}
                className={`flex items-center justify-between px-3 py-2 border rounded-lg ${
                  !schedule.enabled ? "opacity-50 bg-muted" : ""
                }`}
              >
                {/* Left: name, description, next execution */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm truncate">
                      {schedule.name}
                    </span>
                    {schedule.enabled ? (
                      <Badge className="text-xs shrink-0 bg-emerald-500 hover:bg-emerald-600">
                        Enabled
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="text-xs shrink-0">
                        Disabled
                      </Badge>
                    )}
                    {schedule.prompt && (
                      <Badge variant="outline" className="text-xs shrink-0">
                        Custom prompt
                      </Badge>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {schedule.description}
                  </div>
                  {schedule.enabled && schedule.next_execution && (
                    <div className="flex items-center gap-1 text-xs text-muted-foreground mt-0.5">
                      <Clock className="h-3 w-3" />
                      Next: {formatNextExecution(schedule.next_execution)}
                    </div>
                  )}
                </div>
                {/* Right: action buttons */}
                <div className="flex items-center gap-0.5 ml-2 shrink-0">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6"
                          onClick={() => handleEditOpen(schedule)}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        Edit schedule
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6"
                          onClick={() =>
                            toggleMutation.mutate({
                              scheduleId: schedule.id,
                              enabled: !schedule.enabled,
                            })
                          }
                        >
                          {schedule.enabled ? (
                            <Power className="h-3.5 w-3.5 text-emerald-500" />
                          ) : (
                            <PowerOff className="h-3.5 w-3.5 text-muted-foreground" />
                          )}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top" className="text-xs">
                        {schedule.enabled ? "Disable" : "Enable"}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-destructive hover:text-destructive"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Schedule</AlertDialogTitle>
                        <AlertDialogDescription>
                          Are you sure you want to delete &quot;{schedule.name}&quot;?
                          This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => deleteMutation.mutate(schedule.id)}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          Delete
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {/* Edit Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Schedule</DialogTitle>
            <DialogDescription>
              Update the schedule name, timing, or prompt.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-schedule-name">Name</Label>
              <Input
                id="edit-schedule-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Timing</Label>
              {/* Show current schedule info */}
              {editingSchedule && !editGenerated && (
                <div className="bg-secondary p-3 rounded-md space-y-1.5">
                  <div className="flex items-start gap-2">
                    <Check className="h-4 w-4 text-green-600 mt-0.5 shrink-0" />
                    <span className="font-medium text-sm">
                      {editingSchedule.description}
                    </span>
                  </div>
                  {editingSchedule.next_execution && (
                    <div className="flex items-start gap-2 text-sm text-muted-foreground">
                      <Clock className="h-4 w-4 mt-0.5 shrink-0" />
                      <span>
                        Next: {formatNextExecution(editingSchedule.next_execution)}
                      </span>
                    </div>
                  )}
                </div>
              )}
              <div className="flex gap-2">
                <Input
                  value={editInput}
                  onChange={(e) => setEditInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleEditGenerate()}
                  placeholder={
                    editingSchedule
                      ? "Enter new timing to change schedule..."
                      : "e.g., every workday at 7am"
                  }
                  disabled={generateMutation.isPending}
                />
                <Button
                  onClick={handleEditGenerate}
                  disabled={!editInput.trim() || generateMutation.isPending}
                  variant="outline"
                >
                  {generateMutation.isPending ? (
                    "..."
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4 mr-1" />
                      Generate
                    </>
                  )}
                </Button>
              </div>
              {editGenerated && (
                <div className="bg-secondary p-3 rounded-md space-y-1.5">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
                    <span className="font-medium text-sm">
                      New: {editGenerated.description}
                    </span>
                  </div>
                  {editGenerated.next_execution && (
                    <div className="flex items-start gap-2 text-sm text-muted-foreground">
                      <Clock className="h-4 w-4 mt-0.5 shrink-0" />
                      <span>
                        Next: {formatNextExecution(editGenerated.next_execution)}
                      </span>
                    </div>
                  )}
                </div>
              )}
              {editError && (
                <div className="bg-destructive/10 border border-destructive/20 p-3 rounded-md">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
                    <span className="text-sm text-destructive">
                      {editError}
                    </span>
                  </div>
                </div>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-schedule-prompt">Prompt (optional)</Label>
              <Textarea
                id="edit-schedule-prompt"
                placeholder="Leave empty to use agent's entrypoint prompt"
                value={editPrompt}
                onChange={(e) => setEditPrompt(e.target.value)}
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleEditSave}
              disabled={!editName.trim() || updateMutation.isPending}
            >
              {updateMutation.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
