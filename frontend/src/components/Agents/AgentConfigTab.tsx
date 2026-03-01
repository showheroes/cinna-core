import { useState } from "react"

import type { AgentPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { AgentSchedulesCard } from "./AgentSchedulesCard"
import { AgentHandovers } from "./AgentHandovers"
import { EditDescriptionModal } from "./EditDescriptionModal"
import { EditEntrypointPromptModal } from "./EditEntrypointPromptModal"
import { EditWorkflowPromptModal } from "./EditWorkflowPromptModal"
import { EditRefinerPromptModal } from "./EditRefinerPromptModal"
import { EditExamplePromptsModal } from "./EditExamplePromptsModal"

interface AgentConfigTabProps {
  agent: AgentPublic
  readOnly?: boolean
}

export function AgentConfigTab({ agent, readOnly = false }: AgentConfigTabProps) {
  // Modal state
  const [descriptionModalOpen, setDescriptionModalOpen] = useState(false)
  const [entrypointModalOpen, setEntrypointModalOpen] = useState(false)
  const [workflowModalOpen, setWorkflowModalOpen] = useState(false)
  const [refinerModalOpen, setRefinerModalOpen] = useState(false)
  const [examplePromptsModalOpen, setExamplePromptsModalOpen] = useState(false)

  return (
    <div className="space-y-6">
      {/* Top Row: Information and Agent Prompts (side by side) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Information Card */}
        <Card>
          <CardHeader>
            <CardTitle>Information</CardTitle>
            <CardDescription>
              Basic information about this agent
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant="outline"
                onClick={() => setDescriptionModalOpen(true)}
              >
                Description
              </Button>
              <Button
                variant="outline"
                onClick={() => setExamplePromptsModalOpen(true)}
              >
                Example Prompts
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Agent Prompts Card */}
        <Card>
          <CardHeader>
            <CardTitle>Agent Prompts</CardTitle>
            <CardDescription>
              Configure the prompts that define how this agent behaves
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant="outline"
                onClick={() => setEntrypointModalOpen(true)}
              >
                Entrypoint Prompt
              </Button>
              <Button
                variant="outline"
                onClick={() => setWorkflowModalOpen(true)}
              >
                Workflow Prompt
              </Button>
              <Button
                variant="outline"
                onClick={() => setRefinerModalOpen(true)}
              >
                Refiner Prompt
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Third Row: Scheduler and Handovers (side by side) */}
      {/* Note: Scheduler and Handovers are always editable for agent owner (including clone owners) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Schedules Card */}
        <AgentSchedulesCard agentId={agent.id} />

        {/* Handover to Agents - always editable for agent owner (including clone owners) */}
        <AgentHandovers agent={agent} />
      </div>

      {/* Modals */}
      <EditDescriptionModal
        agentId={agent.id}
        currentDescription={agent.description}
        open={descriptionModalOpen}
        onClose={() => setDescriptionModalOpen(false)}
        readOnly={readOnly}
      />
      <EditEntrypointPromptModal
        agentId={agent.id}
        currentPrompt={agent.entrypoint_prompt}
        open={entrypointModalOpen}
        onClose={() => setEntrypointModalOpen(false)}
        readOnly={readOnly}
      />
      <EditWorkflowPromptModal
        agentId={agent.id}
        currentPrompt={agent.workflow_prompt}
        open={workflowModalOpen}
        onClose={() => setWorkflowModalOpen(false)}
        readOnly={readOnly}
      />
      <EditRefinerPromptModal
        agentId={agent.id}
        currentPrompt={agent.refiner_prompt}
        open={refinerModalOpen}
        onClose={() => setRefinerModalOpen(false)}
        readOnly={readOnly}
      />
      <EditExamplePromptsModal
        agentId={agent.id}
        currentPrompts={agent.example_prompts}
        open={examplePromptsModalOpen}
        onClose={() => setExamplePromptsModalOpen(false)}
        readOnly={readOnly}
      />
    </div>
  )
}
