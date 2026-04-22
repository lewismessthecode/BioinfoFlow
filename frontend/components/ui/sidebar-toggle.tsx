"use client"

import { PanelLeftClose, PanelLeft, PanelRightClose, PanelRight, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface SidebarToggleProps {
  side: "left" | "right"
  collapsed: boolean
  onToggle: () => void
  className?: string
}

const iconMap: Record<string, LucideIcon> = {
  "left-collapsed": PanelLeft,
  "left-expanded": PanelLeftClose,
  "right-collapsed": PanelRight,
  "right-expanded": PanelRightClose,
}

export function SidebarToggle({ side, collapsed, onToggle, className }: SidebarToggleProps) {
  const iconKey = `${side}-${collapsed ? "collapsed" : "expanded"}`
  const Icon = iconMap[iconKey]

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={onToggle}
      className={cn("h-8 w-8 text-muted-foreground hover:text-foreground", className)}
      title={collapsed ? `Show ${side} sidebar` : `Hide ${side} sidebar`}
      aria-label={collapsed ? `Show ${side} sidebar` : `Hide ${side} sidebar`}
    >
      <Icon className="h-4 w-4" />
    </Button>
  )
}
