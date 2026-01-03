import {
  BarChart3,
  TrendingUp,
  DollarSign,
  CreditCard,
  PieChart,
  LineChart,
  Database,
  Table,
  FileSpreadsheet,
  Mail,
  Users,
  ShoppingCart,
  Briefcase,
  Building2,
  Rocket,
  Layers,
  Zap,
  Target,
  Calendar,
  FolderKanban,
  type LucideIcon,
} from "lucide-react"

export interface WorkspaceIconOption {
  name: string
  icon: LucideIcon
  label: string
  theme: string
}

export const WORKSPACE_ICONS: WorkspaceIconOption[] = [
  { name: "bar-chart", icon: BarChart3, label: "Bar Chart", theme: "analytics" },
  { name: "trending-up", icon: TrendingUp, label: "Trending Up", theme: "analytics" },
  { name: "pie-chart", icon: PieChart, label: "Pie Chart", theme: "analytics" },
  { name: "line-chart", icon: LineChart, label: "Line Chart", theme: "analytics" },
  { name: "dollar-sign", icon: DollarSign, label: "Dollar Sign", theme: "financial" },
  { name: "credit-card", icon: CreditCard, label: "Credit Card", theme: "financial" },
  { name: "database", icon: Database, label: "Database", theme: "data" },
  { name: "table", icon: Table, label: "Table", theme: "data" },
  { name: "spreadsheet", icon: FileSpreadsheet, label: "Spreadsheet", theme: "data" },
  { name: "mail", icon: Mail, label: "Mail", theme: "communication" },
  { name: "users", icon: Users, label: "Users", theme: "people" },
  { name: "shopping-cart", icon: ShoppingCart, label: "Shopping Cart", theme: "ecommerce" },
  { name: "briefcase", icon: Briefcase, label: "Briefcase", theme: "business" },
  { name: "building", icon: Building2, label: "Building", theme: "business" },
  { name: "rocket", icon: Rocket, label: "Rocket", theme: "startup" },
  { name: "layers", icon: Layers, label: "Layers", theme: "general" },
  { name: "zap", icon: Zap, label: "Zap", theme: "productivity" },
  { name: "target", icon: Target, label: "Target", theme: "goals" },
  { name: "calendar", icon: Calendar, label: "Calendar", theme: "scheduling" },
  { name: "folder-kanban", icon: FolderKanban, label: "Folder Kanban", theme: "general" },
]

export const getWorkspaceIcon = (iconName: string | null | undefined): LucideIcon => {
  if (!iconName) return FolderKanban
  const iconOption = WORKSPACE_ICONS.find((icon) => icon.name === iconName)
  return iconOption?.icon || FolderKanban
}
