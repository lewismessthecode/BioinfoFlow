"use client"

import { useTranslations } from "next-intl"
import { AlertTriangle } from "@/lib/icons"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { RunError } from "@/lib/types"

interface RunErrorCardProps {
  error: RunError | null | undefined
  className?: string
}

export function RunErrorCard({ error, className }: RunErrorCardProps) {
  const t = useTranslations("runs.error")
  if (!error) return null

  return (
    <div
      className={cn(
        "rounded-lg border border-destructive/40 bg-destructive/5 p-4",
        className,
      )}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="size-5 shrink-0 text-destructive" />
        <div className="flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="destructive" className="font-mono text-[10px]">
              {error.code}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {t(`stage.${error.stage}`)}
            </Badge>
          </div>
          <p className="text-sm font-medium text-foreground">{error.message}</p>
          {error.hint ? (
            <p className="text-xs text-muted-foreground">{error.hint}</p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
