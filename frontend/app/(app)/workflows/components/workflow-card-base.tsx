"use client"

import { useTranslations } from "next-intl"
import { MoreHorizontal, Clock } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

interface WorkflowCardBaseProps {
  /** Display name shown in the card header */
  displayName: string
  /** Optional wrapper around the name+icon area (e.g. Tooltip) */
  nameWrapper?: (children: React.ReactNode) => React.ReactNode
  /** Content between header and time (e.g. description, pills) */
  children?: React.ReactNode
  /** Estimated time label */
  estimatedTime?: string | null
  /** Dropdown menu items */
  menuItems: React.ReactNode
  /** Bottom action buttons */
  actions: React.ReactNode
}

function WorkflowIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={cn("h-3.5 w-3.5 text-foreground/70", className)} fill="currentColor">
      <path d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.18l6.9 3.45L12 11.09 5.1 7.63 12 4.18zM4 16.54V9.09l7 3.5v7.45l-7-3.5zm9 3.5v-7.45l7-3.5v7.45l-7 3.5z" />
    </svg>
  )
}

export function WorkflowCardBase({
  displayName,
  nameWrapper,
  children,
  estimatedTime,
  menuItems,
  actions,
}: WorkflowCardBaseProps) {
  const tCommon = useTranslations("common")

  const nameContent = (
    <div className="flex items-center gap-2.5 min-w-0">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border/60 bg-secondary/50 dark:bg-secondary/30">
        <WorkflowIcon />
      </div>
      <h3 className="text-sm font-semibold text-foreground leading-tight truncate">{displayName}</h3>
    </div>
  )

  return (
    <Card className="group relative overflow-hidden border-border/60 bg-card/70 hover:shadow-md hover:border-primary/20 transition-all duration-200 h-full flex flex-col">
      <CardContent className="p-4 flex-1 flex flex-col">
        {/* Header: icon + name + menu */}
        <div className="flex items-center justify-between gap-2">
          {nameWrapper ? nameWrapper(nameContent) : nameContent}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100 shrink-0"
                aria-label={tCommon("actions")}
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {menuItems}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Slot for description, pills, etc. */}
        {children}

        {/* Time */}
        <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {estimatedTime || "\u2014"}
        </div>

        {/* Actions */}
        <div className="mt-auto pt-1 grid grid-cols-2 gap-2">
          {actions}
        </div>
      </CardContent>
    </Card>
  )
}
