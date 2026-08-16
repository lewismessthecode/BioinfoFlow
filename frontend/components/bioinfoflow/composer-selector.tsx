"use client"

import type { ComponentProps, ReactNode } from "react"

import {
  composerSelectorChipClassName,
  composerSelectorMenuClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import { Button } from "@/components/ui/button"
import { DropdownMenuContent } from "@/components/ui/dropdown-menu"
import { PopoverContent } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

type ComposerSelectorTriggerProps = ComponentProps<typeof Button> & {
  composer?: boolean
}

export function ComposerSelectorTrigger({
  composer = true,
  className,
  ...props
}: ComposerSelectorTriggerProps) {
  return (
    <Button
      {...props}
      data-composer-selector-trigger={composer ? "true" : undefined}
      className={cn(
        composer && composerSelectorChipClassName,
        composer && "h-8 min-h-8 lg:h-8",
        className,
      )}
    />
  )
}

type ComposerSelectorMenuSurfaceProps = {
  kind: "dropdown" | "popover"
  composer?: boolean
  children: ReactNode
  className?: string
  align?: "start" | "center" | "end"
  side?: "top" | "right" | "bottom" | "left"
  sideOffset?: number
}

export function ComposerSelectorMenuSurface({
  kind,
  composer = true,
  children,
  className,
  align = "start",
  side = "top",
  sideOffset = 10,
}: ComposerSelectorMenuSurfaceProps) {
  const surfaceProps = {
    align,
    side,
    sideOffset,
    className: cn(composer && composerSelectorMenuClassName, className),
    "data-testid": composer ? "composer-selector-menu" : undefined,
    children,
  }

  return kind === "popover" ? (
    <PopoverContent {...surfaceProps} />
  ) : (
    <DropdownMenuContent {...surfaceProps} />
  )
}
