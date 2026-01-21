import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { AgentSharesService } from "@/client"
import type { PendingSharePublic } from "@/client"

import { WizardStepOverview } from "./WizardStepOverview"
import { WizardStepAICredentials } from "./WizardStepAICredentials"
import { WizardStepCredentials, type CredentialSelection } from "./WizardStepCredentials"
import { WizardStepConfirm } from "./WizardStepConfirm"

// Re-export for consumers
export type { CredentialSelection }

interface AcceptShareWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  share: PendingSharePublic
  onComplete: () => void
}

interface AICredentialSelections {
  conversationCredentialId: string | null
  buildingCredentialId: string | null
}

type WizardStep = "overview" | "ai_credentials" | "credentials" | "confirm"

export function AcceptShareWizard({
  open,
  onOpenChange,
  share,
  onComplete,
}: AcceptShareWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>("overview")
  const [credentialSelections, setCredentialSelections] = useState<
    Record<string, CredentialSelection>
  >({})
  const [aiCredentialSelections, setAICredentialSelections] = useState<AICredentialSelections>({
    conversationCredentialId: null,
    buildingCredentialId: null,
  })

  // Convert credential selections to the format expected by the backend
  const buildCredentialsPayload = (): Record<string, string> | undefined => {
    const payload: Record<string, string> = {}
    let hasSelections = false

    for (const [credName, selection] of Object.entries(credentialSelections)) {
      // Only include if user selected their own credential (not "use shared" and not empty)
      if (selection.selectedCredentialId && selection.selectedCredentialId !== "__create_new__") {
        payload[credName] = selection.selectedCredentialId
        hasSelections = true
      }
    }

    return hasSelections ? payload : undefined
  }

  const acceptMutation = useMutation({
    mutationFn: () =>
      AgentSharesService.acceptShare({
        shareId: share.id,
        requestBody: {
          credentials: buildCredentialsPayload(),
          ai_credential_selections: aiCredentialSelections.conversationCredentialId || aiCredentialSelections.buildingCredentialId
            ? {
                conversation_credential_id: aiCredentialSelections.conversationCredentialId || undefined,
                building_credential_id: aiCredentialSelections.buildingCredentialId || undefined,
              }
            : undefined,
        },
      }),
    onSuccess: () => {
      onComplete()
      resetWizard()
    },
  })

  const resetWizard = () => {
    setCurrentStep("overview")
    setCredentialSelections({})
    setAICredentialSelections({
      conversationCredentialId: null,
      buildingCredentialId: null,
    })
  }

  // Show credentials step if there are any credentials required
  const hasCredentialsRequired = (share.credentials_required?.length ?? 0) > 0

  // Determine if AI credentials step is needed
  // Skip if owner provided AI credentials OR if no AI credential types required
  const needsAICredentialStep =
    !share.ai_credentials_provided &&
    (share.required_ai_credential_types?.length ?? 0) > 0

  const handleNext = () => {
    if (currentStep === "overview") {
      if (needsAICredentialStep) {
        setCurrentStep("ai_credentials")
      } else if (hasCredentialsRequired) {
        setCurrentStep("credentials")
      } else {
        setCurrentStep("confirm")
      }
    } else if (currentStep === "ai_credentials") {
      if (hasCredentialsRequired) {
        setCurrentStep("credentials")
      } else {
        setCurrentStep("confirm")
      }
    } else if (currentStep === "credentials") {
      setCurrentStep("confirm")
    }
  }

  const handleBack = () => {
    if (currentStep === "confirm") {
      if (hasCredentialsRequired) {
        setCurrentStep("credentials")
      } else if (needsAICredentialStep) {
        setCurrentStep("ai_credentials")
      } else {
        setCurrentStep("overview")
      }
    } else if (currentStep === "credentials") {
      if (needsAICredentialStep) {
        setCurrentStep("ai_credentials")
      } else {
        setCurrentStep("overview")
      }
    } else if (currentStep === "ai_credentials") {
      setCurrentStep("overview")
    }
  }

  const handleCredentialSelectionsChange = (
    selections: Record<string, CredentialSelection>
  ) => {
    setCredentialSelections(selections)
  }

  const handleAICredentialsChange = (selections: AICredentialSelections) => {
    setAICredentialSelections(selections)
  }

  const handleAccept = () => {
    acceptMutation.mutate()
  }

  const handleClose = () => {
    onOpenChange(false)
    resetWizard()
  }

  // Calculate step numbers
  const totalSteps = 1 + (needsAICredentialStep ? 1 : 0) + (hasCredentialsRequired ? 1 : 0) + 1 // overview + ai_creds? + creds? + confirm
  let currentStepNumber = 1
  if (currentStep === "ai_credentials") {
    currentStepNumber = 2
  } else if (currentStep === "credentials") {
    currentStepNumber = needsAICredentialStep ? 3 : 2
  } else if (currentStep === "confirm") {
    currentStepNumber = totalSteps
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Accept Shared Agent: {share.original_agent_name}
          </DialogTitle>
        </DialogHeader>

        {/* Step indicator */}
        <div className="flex items-center justify-center gap-2 py-4">
          <StepIndicator
            step={1}
            label="Overview"
            active={currentStep === "overview"}
            completed={currentStepNumber > 1}
          />
          {needsAICredentialStep && (
            <>
              <StepConnector />
              <StepIndicator
                step={2}
                label="AI Credentials"
                active={currentStep === "ai_credentials"}
                completed={currentStepNumber > 2}
              />
            </>
          )}
          {hasCredentialsRequired && (
            <>
              <StepConnector />
              <StepIndicator
                step={needsAICredentialStep ? 3 : 2}
                label="Credentials"
                active={currentStep === "credentials"}
                completed={currentStepNumber > (needsAICredentialStep ? 3 : 2)}
              />
            </>
          )}
          <StepConnector />
          <StepIndicator
            step={totalSteps}
            label="Confirm"
            active={currentStep === "confirm"}
            completed={false}
          />
        </div>

        {/* Step content */}
        {currentStep === "overview" && (
          <WizardStepOverview
            share={share}
            onNext={handleNext}
            onCancel={handleClose}
          />
        )}

        {currentStep === "ai_credentials" && (
          <WizardStepAICredentials
            share={share}
            aiCredentialSelections={aiCredentialSelections}
            onChange={handleAICredentialsChange}
            onNext={handleNext}
            onBack={handleBack}
          />
        )}

        {currentStep === "credentials" && (
          <WizardStepCredentials
            share={share}
            credentialSelections={credentialSelections}
            onChange={handleCredentialSelectionsChange}
            onNext={handleNext}
            onBack={handleBack}
          />
        )}

        {currentStep === "confirm" && (
          <WizardStepConfirm
            share={share}
            credentialSelections={credentialSelections}
            onAccept={handleAccept}
            onBack={handleBack}
            isLoading={acceptMutation.isPending}
            error={
              acceptMutation.error instanceof Error
                ? acceptMutation.error.message
                : acceptMutation.error
                  ? String(acceptMutation.error)
                  : undefined
            }
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function StepIndicator({
  step,
  label,
  active,
  completed,
}: {
  step: number
  label: string
  active: boolean
  completed: boolean
}) {
  return (
    <div
      className={`flex items-center gap-2 ${active ? "text-primary" : "text-muted-foreground"}`}
    >
      <div
        className={`
        w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
        ${active ? "bg-primary text-primary-foreground" : completed ? "bg-primary/20 text-primary" : "bg-muted"}
      `}
      >
        {step}
      </div>
      <span className="text-sm hidden sm:inline">{label}</span>
    </div>
  )
}

function StepConnector() {
  return <span className="mx-2 text-muted-foreground">-</span>
}
