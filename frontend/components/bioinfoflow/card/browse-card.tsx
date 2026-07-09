"use client"

import type { ElementType, ReactNode } from "react"
import type { AppIcon } from "@/lib/icons"
import { Card, CardContent } from "@/components/ui/card"
import { Icon as AppIconGlyph } from "@/components/ui/icon"
import { cn } from "@/lib/utils"

type BrowseCardProps = {
  title: string
  icon: AppIcon
  iconVariant?: "default" | "artifact"
  titleAs?: "h2" | "h3"
  titleWrapper?: (children: ReactNode) => ReactNode
  menu?: ReactNode
  metadata?: ReactNode
  footerMeta?: ReactNode
  actions?: ReactNode
  actionColumns?: 1 | 2
  className?: string
  contentClassName?: string
  titleClassName?: string
  children?: ReactNode
}

export function BrowseCard({
  title,
  icon: Icon,
  iconVariant = "default",
  titleAs = "h3",
  titleWrapper,
  menu,
  metadata,
  footerMeta,
  actions,
  actionColumns = 2,
  className,
  contentClassName,
  titleClassName,
  children,
}: BrowseCardProps) {
  const TitleTag = titleAs as ElementType
  const titleContent = (
    <div className="flex min-w-0 w-full items-center gap-2.5">
      <div
        className={cn(
          "quiet-card-icon-shell shrink-0",
          iconVariant === "artifact" && "quiet-card-icon-shell--artifact",
        )}
      >
        <AppIconGlyph icon={Icon} className="quiet-card-icon-glyph" />
      </div>
      <TitleTag
        className={cn(
          "min-w-0 text-sm font-semibold text-foreground leading-tight",
          titleClassName ?? "truncate",
        )}
      >
        {title}
      </TitleTag>
    </div>
  )

  return (
    <Card
      data-slot="browse-card"
      className={cn(
        "group relative overflow-hidden border-border/60 bg-card/84 hover:shadow-sm hover:border-border/90 transition-[background-color,border-color,box-shadow] duration-200 h-full flex flex-col",
        className,
      )}
    >
      <CardContent className={cn("p-4 flex-1 flex flex-col", contentClassName)}>
        <div data-slot="browse-card-header" className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            {titleWrapper ? titleWrapper(titleContent) : titleContent}
          </div>
          {menu}
        </div>

        {metadata}
        {children}
        {footerMeta}

        {actions ? (
          <div
            data-slot="browse-card-actions"
            className={cn(
              "mt-auto pt-3 grid gap-2",
              actionColumns === 1 ? "grid-cols-1" : "grid-cols-2",
            )}
          >
            {actions}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
