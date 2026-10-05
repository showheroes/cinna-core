import type { LucideIcon } from "lucide-react"
import { Globe, Lock, Users } from "lucide-react"

import type { KnowledgeSourceAccessLevel } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"

interface AccessLevelOption {
  value: KnowledgeSourceAccessLevel
  label: string
  description: string
  icon: LucideIcon
}

// Who may query a source (agents, CLI knowledge search). Superusers manage
// every source regardless of level.
export const ACCESS_LEVEL_OPTIONS: AccessLevelOption[] = [
  {
    value: "private",
    label: "Private",
    description: "Admins only",
    icon: Lock,
  },
  {
    value: "public",
    label: "Public",
    description: "Every user on the server",
    icon: Globe,
  },
  {
    value: "shared",
    label: "Shared",
    description: "Selected users and admins",
    icon: Users,
  },
]

function optionFor(level: KnowledgeSourceAccessLevel | undefined) {
  return (
    ACCESS_LEVEL_OPTIONS.find((o) => o.value === level) ??
    ACCESS_LEVEL_OPTIONS[0]
  )
}

export function AccessLevelBadge({
  level,
  sharedUserCount,
}: {
  level: KnowledgeSourceAccessLevel | undefined
  sharedUserCount?: number
}) {
  const option = optionFor(level)
  const Icon = option.icon
  const suffix =
    option.value === "shared" && sharedUserCount !== undefined
      ? ` · ${sharedUserCount} ${sharedUserCount === 1 ? "user" : "users"}`
      : ""
  return (
    <Badge variant="outline" className="font-normal">
      <Icon className="mr-1 h-3 w-3" />
      {option.label}
      {suffix}
    </Badge>
  )
}

interface AccessLevelRadioGroupProps {
  value: KnowledgeSourceAccessLevel
  onChange: (value: KnowledgeSourceAccessLevel) => void
  disabled?: boolean
  idPrefix: string
}

export function AccessLevelRadioGroup({
  value,
  onChange,
  disabled,
  idPrefix,
}: AccessLevelRadioGroupProps) {
  return (
    <RadioGroup
      value={value}
      onValueChange={(next) => onChange(next as KnowledgeSourceAccessLevel)}
      disabled={disabled}
      className="gap-3"
    >
      {ACCESS_LEVEL_OPTIONS.map((option) => {
        const id = `${idPrefix}-${option.value}`
        return (
          <div key={option.value} className="flex items-start gap-2">
            <RadioGroupItem value={option.value} id={id} className="mt-0.5" />
            <Label
              htmlFor={id}
              className="flex flex-col items-start gap-0.5 font-normal cursor-pointer"
            >
              <span className="text-sm font-medium">{option.label}</span>
              <span className="text-xs text-muted-foreground">
                {option.description}
              </span>
            </Label>
          </div>
        )
      })}
    </RadioGroup>
  )
}
