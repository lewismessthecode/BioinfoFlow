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
  presentation?: "default" | "composer"
}

export function ComposerSelectorTrigger({
  presentation = "composer",
  className,
  ...props
}: ComposerSelectorTriggerProps) {
  const isComposer = presentation === "composer"
  return (
    <Button
      {...props}
      data-composer-selector-trigger={isComposer ? "true" : undefined}
      className={cn(
        isComposer && composerSelectorChipClassName,
        isComposer && "h-8 min-h-8 lg:h-8",
        className,
      )}
    />
  )
}

type ComposerSelectorMenuSurfaceProps = {
  kind: "dropdown" | "popover"
  presentation?: "default" | "composer"
  children: ReactNode
  className?: string
  align?: "start" | "center" | "end"
  side?: "top" | "right" | "bottom" | "left"
  sideOffset?: number
}

export function ComposerSelectorMenuSurface({
  kind,
  presentation = "composer",
  children,
  className,
  align = "start",
  side = "top",
  sideOffset = 10,
}: ComposerSelectorMenuSurfaceProps) {
  const isComposer = presentation === "composer"
  const surfaceProps = {
    align,
    side,
    sideOffset,
    className: cn(isComposer && composerSelectorMenuClassName, className),
    "data-testid": isComposer ? "composer-selector-menu" : undefined,
    children,
  }

  return kind === "popover" ? (
    <PopoverContent {...surfaceProps} />
  ) : (
    <DropdownMenuContent {...surfaceProps} />
  )
}
