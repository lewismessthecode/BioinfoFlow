"use client"

import { useTranslations } from "next-intl"
import { MoreHorizontal, Clock, Workflow } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { BrowseCard } from "@/components/bioinfoflow/card/browse-card"

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

export function WorkflowCardBase({
  displayName,
  nameWrapper,
  children,
  estimatedTime,
  menuItems,
  actions,
}: WorkflowCardBaseProps) {
  const tCommon = useTranslations("common")

  return (
    <BrowseCard
      title={displayName}
      icon={Workflow}
      titleWrapper={nameWrapper}
      menu={
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
      }
      footerMeta={
        <div className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          {estimatedTime || "\u2014"}
        </div>
      }
      actions={actions}
    >
        {children}
    </BrowseCard>
  )
}
