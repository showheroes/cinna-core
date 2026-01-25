import { formatDistanceToNow } from "date-fns"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface RelativeTimeProps {
  timestamp: string | Date
  fallback?: string
  className?: string
  /** Display as a badge/chip with background color */
  asBadge?: boolean
  /** Icon to display before the text (pass a lucide-react component) */
  icon?: React.ReactNode
  /** Show tooltip with full date on hover */
  showTooltip?: boolean
  /** Color code badge based on time thresholds (e.g., recent activity) */
  colorCode?: boolean
  /** Tooltip content override (defaults to full date/time) */
  tooltipContent?: string
}

/**
 * Component to display relative time (e.g., "2 minutes ago", "3 hours ago")
 * with robust timestamp handling and graceful error fallback.
 *
 * Can be displayed as a simple span or as a colored badge with icon and tooltip.
 */
export function RelativeTime({
  timestamp,
  fallback = "recently",
  className = "",
  asBadge = false,
  icon,
  showTooltip = false,
  colorCode = false,
  tooltipContent
}: RelativeTimeProps) {
  const { formattedTime, date, fullDate } = (() => {
    try {
      // Handle timestamp - it might already have 'Z'
      const timestampStr = typeof timestamp === 'string'
        ? (timestamp.endsWith('Z') ? timestamp : timestamp + 'Z')
        : timestamp
      const dateObj = new Date(timestampStr)

      if (isNaN(dateObj.getTime())) {
        return { formattedTime: fallback, date: null, fullDate: "" }
      }

      const formatted = formatDistanceToNow(dateObj, { addSuffix: true })
      const full = dateObj.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      })

      return { formattedTime: formatted, date: dateObj, fullDate: full }
    } catch {
      return { formattedTime: fallback, date: null, fullDate: "" }
    }
  })()

  // Get badge color based on how recent the timestamp is
  const getBadgeColor = (): string => {
    if (!colorCode || !date) return "bg-muted text-muted-foreground border-border"

    const now = new Date()
    const minutesAgo = Math.floor((now.getTime() - date.getTime()) / (1000 * 60))
    const hoursAgo = Math.floor(minutesAgo / 60)
    const daysAgo = Math.floor(hoursAgo / 24)

    if (minutesAgo < 5) {
      // Very recent (< 5 minutes)
      return "bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800"
    } else if (minutesAgo < 30) {
      // Recent (< 30 minutes)
      return "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800"
    } else if (hoursAgo < 24) {
      // Today (< 24 hours)
      return "bg-violet-100 dark:bg-violet-950 text-violet-700 dark:text-violet-300 border-violet-200 dark:border-violet-800"
    } else if (daysAgo < 7) {
      // This week (< 7 days)
      return "bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800"
    } else {
      // Older
      return "bg-muted text-muted-foreground border-border"
    }
  }

  const content = (
    <span className={asBadge ? `flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs shrink-0 ${getBadgeColor()}` : className}>
      {icon && <span className="shrink-0">{icon}</span>}
      <span>{formattedTime}</span>
    </span>
  )

  if (showTooltip || tooltipContent) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            {content}
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs">
            {tooltipContent || fullDate}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return content
}
