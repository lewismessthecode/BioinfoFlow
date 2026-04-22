import type { LucideIcon } from "lucide-react"
import {
  Bot,
  Container,
  Gauge,
  GitBranch,
  LayoutDashboard,
  Play,
  Settings,
} from "lucide-react"

/** Single source of truth for top-level app navigation routes. */
type NavRoute = {
  key: string
  href: string
  icon: LucideIcon
}

export const NAV_ROUTES: readonly NavRoute[] = [
  { key: "dashboard", href: "/dashboard", icon: LayoutDashboard },
  { key: "agent", href: "/agent", icon: Bot },
  { key: "workflows", href: "/workflows", icon: GitBranch },
  { key: "runs", href: "/runs", icon: Play },
  { key: "images", href: "/images", icon: Container },
  { key: "scheduler", href: "/scheduler", icon: Gauge },
  { key: "settings", href: "/settings", icon: Settings },
] as const
