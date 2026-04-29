"use client"

import { useTranslations } from "next-intl"
import { MoreHorizontal, Clock, Workflow } from "lucide-react"
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
    <Workflow className={cn("quiet-card-icon-glyph h-4 w-4", className)} strokeWidth={1.8} />
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
    <div className="flex min-w-0 w-full items-center gap-2.5">
      <div className="quiet-card-icon-shell shrink-0">
        <WorkflowIcon />
      </div>
      <h3 className="min-w-0 truncate text-sm font-semibold text-foreground leading-tight">{displayName}</h3>
    </div>
  )

  return (
    <Card className="group relative overflow-hidden border-border/60 bg-card/84 hover:shadow-sm hover:border-border/90 transition-all duration-200 h-full flex flex-col">
      <CardContent className="p-4 flex-1 flex flex-col">
        {/* Header: icon + name + menu */}
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 flex-1">
            {nameWrapper ? nameWrapper(nameContent) : nameContent}
          </div>
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
