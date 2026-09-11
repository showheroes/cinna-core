import { useLocation, useNavigate } from "@tanstack/react-router"
import { useEffect, ReactNode } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export interface TabConfig {
  value: string
  title: string
  content: ReactNode
}

interface HashTabsProps {
  tabs: TabConfig[]
  defaultTab?: string
  /**
   * The active tab, whenever it changes — including the initial one.
   *
   * For a host that has to render something of its own per tab: the AI
   * Credentials route puts each tab's primary button (and the managed tab's
   * Filter button) in the **page header**, which is outside the `Tabs` tree,
   * so it cannot read the active tab from context. Fired from an effect rather
   * than from the click handler so a deep link (`#providers`) and a browser
   * Back that changes the hash both report, not just a click on the strip.
   */
  onTabChange?: (value: string) => void
}

export function HashTabs({ tabs, defaultTab, onTabChange }: HashTabsProps) {
  // Router state updates for both browser hash changes and in-app Links. The
  // latter do not dispatch `hashchange`, so window event listeners leave a
  // same-page link pointing at the old tab.
  const hash = useLocation({ select: (location) => location.hash })
  const navigate = useNavigate()
  const validTabs = tabs.map((tab) => tab.value)
  const activeTab = validTabs.includes(hash)
    ? hash
    : defaultTab || tabs[0]?.value || ""

  // Update hash when tab changes
  const handleTabChange = (value: string) => {
    void navigate({ hash: value })
  }

  useEffect(() => {
    onTabChange?.(activeTab)
  }, [activeTab, onTabChange])

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange}>
      <TabsList>
        {tabs.map((tab) => (
          <TabsTrigger key={tab.value} value={tab.value}>
            {tab.title}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((tab) => (
        <TabsContent key={tab.value} value={tab.value}>
          {tab.content}
        </TabsContent>
      ))}
    </Tabs>
  )
}
