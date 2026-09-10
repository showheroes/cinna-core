import {
  Link,
  type RegisteredRouter,
  type ValidateLinkOptions,
} from "@tanstack/react-router"
import { ExternalLink } from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export interface NewTabIconLinkProps<
  TRouter extends RegisteredRouter = RegisteredRouter,
  TOptions = unknown,
> {
  /** Tooltip and `aria-label`. Say what opens, and that it is a new tab. */
  label: string
  /** The in-app destination, type-checked like a `Link`'s own props. */
  linkOptions: ValidateLinkOptions<TRouter, TOptions>
}

/**
 * A row's bare "open this in a new tab" control: a ghost `h-7 w-7` icon button
 * with the `ExternalLink` glyph, a tooltip, and the new-tab attributes.
 *
 * For a control inside a form or a confirm dialog, where following the link
 * in place would throw away what the user is doing. `ExternalLink` is right
 * here and nowhere near a fact list (§2 "Links in a fact list"): the button has
 * no text saying it leaves the page, so the glyph says it.
 */
export function NewTabIconLink<TRouter extends RegisteredRouter, TOptions>(
  props: NewTabIconLinkProps<TRouter, TOptions>,
): ReactNode
export function NewTabIconLink({
  label,
  linkOptions,
}: NewTabIconLinkProps): ReactNode {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button asChild variant="ghost" size="icon" className="h-7 w-7">
          <Link
            {...linkOptions}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={label}
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs">
        {label}
      </TooltipContent>
    </Tooltip>
  )
}
