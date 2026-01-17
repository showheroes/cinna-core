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
import { WizardStepCredentials } from "./WizardStepCredentials"
import { WizardStepConfirm } from "./WizardStepConfirm"

interface AcceptShareWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  share: PendingSharePublic
  onComplete: () => void
}

type WizardStep = "overview" | "credentials" | "confirm"

export function AcceptShareWizard({
  open,
  onOpenChange,
  share,
  onComplete,
}: AcceptShareWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>("overview")
  const [credentialsData, setCredentialsData] = useState<
    Record<string, Record<string, string>>
  >({})

  const acceptMutation = useMutation({
    mutationFn: () =>
      AgentSharesService.acceptShare({
        shareId: share.id,
        requestBody: {
          credentials: credentialsData,
        },
      }),
    onSuccess: () => {
      onComplete()
      resetWizard()
    },
  })

  const resetWizard = () => {
    setCurrentStep("overview")
    setCredentialsData({})
  }

  const needsCredentialSetup =
    share.credentials_required?.some((c) => !c.allow_sharing) ?? false

  const handleNext = () => {
    if (currentStep === "overview") {
      if (needsCredentialSetup) {
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
      if (needsCredentialSetup) {
        setCurrentStep("credentials")
      } else {
        setCurrentStep("overview")
      }
    } else if (currentStep === "credentials") {
      setCurrentStep("overview")
    }
  }

  const handleCredentialsChange = (
    data: Record<string, Record<string, string>>
  ) => {
    setCredentialsData(data)
  }

  const handleAccept = () => {
    acceptMutation.mutate()
  }

  const handleClose = () => {
    onOpenChange(false)
    resetWizard()
  }

  // Calculate step numbers
  const totalSteps = needsCredentialSetup ? 3 : 2
  const currentStepNumber =
    currentStep === "overview"
      ? 1
      : currentStep === "credentials"
        ? 2
        : totalSteps

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
          {needsCredentialSetup && (
            <>
              <StepConnector />
              <StepIndicator
                step={2}
                label="Credentials"
                active={currentStep === "credentials"}
                completed={currentStepNumber > 2}
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

        {currentStep === "credentials" && (
          <WizardStepCredentials
            share={share}
            credentialsData={credentialsData}
            onChange={handleCredentialsChange}
            onNext={handleNext}
            onBack={handleBack}
          />
        )}

        {currentStep === "confirm" && (
          <WizardStepConfirm
            share={share}
            credentialsData={credentialsData}
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
