"use client"

import * as React from "react"
import { cn } from "@/lib/utils"
import type { AppIcon } from "@/lib/icons"
import { Icon as AppIconGlyph } from "@/components/ui/icon"

// Card Root
interface CardRootProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "success" | "error" | "warning" | "workbench"
}

export function CardRoot({ className, variant = "default", ...props }: CardRootProps) {
  return (
    <div
      data-slot="bioflow-card"
      className={cn(
        "rounded-xl border bg-card overflow-hidden",
        variant === "default" && "border-border",
        variant === "success" && "border-success-border",
        variant === "error" && "border-error-border",
        variant === "warning" && "border-amber-200 dark:border-amber-900/50",
        variant === "workbench" && "bif-workbench-card",
        className
      )}
      {...props}
    />
  )
}

// Card Header
interface CardHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: AppIcon
  iconClassName?: string
  title: string
  badge?: React.ReactNode
  action?: React.ReactNode
}

export function CardHeader({
  className,
  icon: Icon,
  iconClassName,
  title,
  badge,
  action,
  ...props
}: CardHeaderProps) {
  return (
    <div
      data-slot="bioflow-card-header"
      className={cn(
        "flex items-center justify-between border-b border-border px-4 py-3",
        className
      )}
      {...props}
    >
      <div className="flex items-center gap-2">
        {Icon && <AppIconGlyph icon={Icon} className={cn("text-foreground", iconClassName)} />}
        <span className="text-sm font-medium text-foreground">{title}</span>
        {badge}
      </div>
      {action}
    </div>
  )
}

// Card Content (main body area)
interface CardContentProps extends React.HTMLAttributes<HTMLDivElement> {
  divided?: boolean
}

export function CardContent({
  className,
  divided,
  children,
  ...props
}: CardContentProps) {
  return (
    <div
      data-slot="bioflow-card-content"
      className={cn(
        "p-4",
        divided && "[&>*:not(:last-child)]:border-b [&>*:not(:last-child)]:border-border [&>*:not(:last-child)]:pb-4 [&>*:not(:first-child)]:pt-4 space-y-0",
        !divided && "space-y-4",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
}
