"use client"

import type { ComponentProps, CSSProperties, ReactNode } from "react"

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

const composerSelectorMetrics = {
  fontSize: 11,
  lineHeight: "16px",
  slotSize: 16,
} as const

export function ComposerSelectorTrigger({
  presentation = "composer",
  className,
  style,
  ...props
}: ComposerSelectorTriggerProps) {
  const isComposer = presentation === "composer"
  return (
    <Button
      {...props}
      data-composer-selector-trigger={isComposer ? "true" : undefined}
      data-composer-selector-metrics={
        isComposer ? "shared" : undefined
      }
      style={
        isComposer
          ? {
              ...style,
              fontSize: composerSelectorMetrics.fontSize,
              lineHeight: composerSelectorMetrics.lineHeight,
            }
          : style
      }
      className={cn(
        isComposer && composerSelectorChipClassName,
        isComposer && "h-11 min-h-11 lg:h-8 lg:min-h-8",
        className,
      )}
    />
  )
}

type ComposerSelectorSlotProps = {
  presentation?: "default" | "composer"
  children: ReactNode
  className?: string
  style?: CSSProperties
}

export function ComposerSelectorIconSlot({
  presentation = "composer",
  children,
  className,
  style,
}: ComposerSelectorSlotProps) {
  const isComposer = presentation === "composer"
  return (
    <span
      data-composer-selector-slot={isComposer ? "icon" : undefined}
      className={cn(
        isComposer &&
          "inline-flex shrink-0 items-center justify-center [&_svg]:size-3",
        className,
      )}
      style={
        isComposer
          ? {
              ...style,
              width: composerSelectorMetrics.slotSize,
              height: composerSelectorMetrics.slotSize,
            }
          : style
      }
    >
      {children}
    </span>
  )
}

export function ComposerSelectorText({
  presentation = "composer",
  children,
  className,
  style,
}: ComposerSelectorSlotProps) {
  const isComposer = presentation === "composer"
  return (
    <span
      data-composer-selector-slot={isComposer ? "text" : undefined}
      className={cn(
        isComposer && "inline-flex min-w-0 items-center truncate",
        className,
      )}
      style={
        isComposer
          ? {
              ...style,
              height: composerSelectorMetrics.slotSize,
              lineHeight: composerSelectorMetrics.lineHeight,
            }
          : style
      }
    >
      {children}
    </span>
  )
}

export function ComposerSelectorChevronSlot({
  presentation = "composer",
  children,
  className,
  style,
}: ComposerSelectorSlotProps) {
  const isComposer = presentation === "composer"
  return (
    <span
      data-composer-selector-slot={isComposer ? "chevron" : undefined}
      className={cn(
        isComposer && "inline-flex size-4 shrink-0 items-center justify-center",
        className,
      )}
      style={
        isComposer
          ? {
              ...style,
              width: composerSelectorMetrics.slotSize,
              height: composerSelectorMetrics.slotSize,
            }
          : style
      }
    >
      {children}
    </span>
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
    "data-composer-selector-menu-density": isComposer
      ? "compact"
      : undefined,
    children,
  }

  return kind === "popover" ? (
    <PopoverContent {...surfaceProps} />
  ) : (
    <DropdownMenuContent {...surfaceProps} />
  )
}
