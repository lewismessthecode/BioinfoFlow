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

type ComposerSelectorFieldProps = ComponentProps<"div"> & {
  feedback?: ReactNode
  feedbackId?: string
  feedbackClassName?: string
}

export function ComposerSelectorField({
  children,
  feedback,
  feedbackId,
  feedbackClassName,
  className,
  ...props
}: ComposerSelectorFieldProps) {
  return (
    <div
      {...props}
      data-composer-selector-field="true"
      className={cn("relative min-w-0 shrink-0", className)}
    >
      {children}
      {feedback ? (
        <div
          id={feedbackId}
          data-composer-selector-feedback="true"
          className={cn(
            "absolute bottom-full left-2 z-20 mb-1.5 max-w-[18rem] rounded-lg border border-border/70 bg-popover px-2 py-1.5 text-[11px] leading-4 text-muted-foreground shadow-[0_8px_24px_rgba(15,15,15,0.06)]",
            feedbackClassName,
          )}
        >
          {feedback}
        </div>
      ) : null}
    </div>
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

type ComposerSelectorOptionContentProps = {
  icon: ReactNode
  title: ReactNode
  description?: ReactNode
  trailing?: ReactNode
  className?: string
  iconClassName?: string
  titleClassName?: string
  descriptionClassName?: string
  trailingClassName?: string
}

export function ComposerSelectorOptionContent({
  icon,
  title,
  description,
  trailing,
  className,
  iconClassName,
  titleClassName,
  descriptionClassName,
  trailingClassName,
}: ComposerSelectorOptionContentProps) {
  return (
    <span
      data-composer-selector-option-content="true"
      className={cn(
        "grid min-w-0 flex-1 grid-cols-[1rem_minmax(0,1fr)_auto] gap-2",
        description ? "items-start" : "items-center",
        className,
      )}
    >
      <span
        className={cn(
          "inline-flex size-4 shrink-0 items-center justify-center [&_svg]:size-3.5",
          iconClassName,
        )}
      >
        {icon}
      </span>
      <span className="grid min-w-0 gap-0.5">
        <span className={cn("truncate font-medium leading-4", titleClassName)}>
          {title}
        </span>
        {description ? (
          <span
            className={cn(
              "whitespace-normal text-[11px] leading-4 text-muted-foreground",
              descriptionClassName,
            )}
          >
            {description}
          </span>
        ) : null}
      </span>
      {trailing ? (
        <span
          className={cn(
            "inline-flex size-4 shrink-0 items-center justify-center",
            trailingClassName,
          )}
        >
          {trailing}
        </span>
      ) : null}
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
