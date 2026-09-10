import { Link } from "@tanstack/react-router"
import { KeyRound } from "lucide-react"
import { useEffect, useRef } from "react"

import type { SkillCredentialProvisionPublic } from "@/client"
import { ListRowGroup } from "@/components/Common/ListRow"
import { Button } from "@/components/ui/button"
import {
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useAgentTabLinkClick } from "@/hooks/useAgentTabLinkClick"
import { slotOutcomeSummary } from "@/utils/skillCredentials"
import { SkillProvisionRow } from "./SkillInstallCredentialsSection"

interface SkillInstallSetupPanelProps {
  skillName: string
  agentId: string
  /** The install response's `credential_provisioning`, ready slots included. */
  items: SkillCredentialProvisionPublic[]
  /** Done (and Escape, through the host): close the host dialog. */
  onClose: () => void
  /**
   * The Credentials tab link was followed. Separate from `onClose` because the
   * link can leave the surface that would have reported anything else.
   */
  onOpenCredentials: () => void
}

/**
 * What an install dialog becomes when the skill went in but some of its
 * credentials still need the user — the one install result that stays on
 * screen (§6: "a state that still needs action stays"). Shown only then; a
 * ready install still toasts and closes.
 *
 * P6's success panel, skeleton by reference to `ShareSkillSuccessPanel`: it
 * replaces the host's header, body and footer in place and **links onward** to
 * the agent's Credentials tab rather than opening anything on top (R8).
 *
 * Every slot is listed, ready ones too, so the list matches the preview the
 * user just read.
 */
export function SkillInstallSetupPanel({
  skillName,
  agentId,
  items,
  onClose,
  onOpenCredentials,
}: SkillInstallSetupPanelProps) {
  const credentialsLinkRef = useRef<HTMLAnchorElement>(null)
  // The Add addon wizard opens this on the agent's own page.
  const followCredentialsTab = useAgentTabLinkClick(agentId, "credentials")

  // The submit button that held focus unmounted with the form, so focus would
  // otherwise fall to the document; put it on the action this panel exists for.
  useEffect(() => {
    credentialsLinkRef.current?.focus()
  }, [])

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex min-w-0 items-center gap-2">
          <KeyRound className="h-5 w-5 shrink-0" />
          <span className="truncate">{skillName} installed</span>
        </DialogTitle>
        <DialogDescription>
          {slotOutcomeSummary(items, "installed")}
        </DialogDescription>
      </DialogHeader>

      <ListRowGroup>
        {items.map((item) => (
          <SkillProvisionRow key={item.slot} item={item} phase="installed" />
        ))}
      </ListRowGroup>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Done
        </Button>
        <Button asChild>
          <Link
            ref={credentialsLinkRef}
            to="/agent/$agentId"
            params={{ agentId }}
            hash="credentials"
            onClick={(event) => {
              followCredentialsTab(event)
              // Prevented means the tab switched in place, leaving the Addons
              // tab behind. A modified click (new tab) leaves this page as it
              // is, so it closes like Done and keeps that path's reporting.
              if (event.defaultPrevented) {
                onOpenCredentials()
              } else {
                onClose()
              }
            }}
          >
            Open the Credentials tab
          </Link>
        </Button>
      </DialogFooter>
    </>
  )
}
