import { useMatchRoute } from "@tanstack/react-router"
import type { MouseEvent } from "react"

/**
 * Click handler for a `Link` to one of an agent's `HashTabs` tabs
 * (`/agent/$agentId#credentials`).
 *
 * `HashTabs` follows the window's `hashchange` event, which a router push never
 * fires. So a link to that tab from **the same agent's page** (the Addons tab's
 * dialogs) would change the URL and leave the tab where it was. When the link
 * points at the page already on screen, this switches the tab through the hash
 * itself — the mechanism `HashTabs` uses for its own strip — and cancels the
 * router push. Anywhere else the `Link` navigates normally, and the tab is read
 * from the hash on mount.
 *
 * Modified clicks (new tab, new window, download) are left to the browser.
 *
 * A workaround, not a pattern: once `HashTabs` follows the router's hash
 * (`useLocation().hash`) instead of the window event, a plain `Link` works on
 * the same page too and this hook can be deleted.
 */
export function useAgentTabLinkClick(agentId: string, tab: string) {
  const matchRoute = useMatchRoute()
  const onAgentPage = !!matchRoute({
    to: "/agent/$agentId",
    params: { agentId },
  })

  return (event: MouseEvent<HTMLAnchorElement>) => {
    if (!onAgentPage) return
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return
    }
    event.preventDefault()
    if (window.location.hash.slice(1) === tab) {
      // Assigning the hash it already has fires nothing, yet the tab can still
      // differ (a router push moved the URL without `HashTabs` hearing it).
      window.dispatchEvent(new HashChangeEvent("hashchange"))
      return
    }
    window.location.hash = tab
  }
}
