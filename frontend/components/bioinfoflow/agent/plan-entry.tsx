"use client"

import { useTranslations } from "next-intl"

import { Check, Circle, Loader2 } from "@/lib/icons"
import { Badge } from "@/components/ui/badge"
import type { PlanEntry, PlanItemStatus } from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

export function AgentPlanEntry({ entry }: { entry: PlanEntry }) {
  const t = useTranslations("agentHistory")
  const total = entry.payload.items.length
  const completed = entry.payload.items.filter(
    (item) => item.status === "completed",
  ).length

  return (
    <section className="grid gap-3 border-y border-border/60 py-3 [content-visibility:auto] [contain-intrinsic-size:auto_128px]">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <h2 className="truncate text-sm font-semibold text-foreground">
          {entry.payload.title ?? t("plan.title")}
        </h2>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {t("plan.progress", { completed, total })}
        </span>
      </div>
      <ol className="grid gap-2">
        {entry.payload.items.map((item) => (
          <li key={item.id} className="flex min-w-0 items-start gap-2.5 text-sm">
            <PlanStatusIcon status={item.status} />
            <span
              className={cn(
                "min-w-0 flex-1 break-words leading-5",
                item.status === "completed" && "text-muted-foreground",
                item.status === "in_progress" && "font-medium text-foreground",
                item.status === "pending" && "text-foreground/72",
              )}
            >
              {item.text}
            </span>
            <Badge variant="outline" className="shrink-0 text-[10px]">
              {t(`plan.status.${item.status}`)}
            </Badge>
          </li>
        ))}
      </ol>
    </section>
  )
}

function PlanStatusIcon({ status }: { status: PlanItemStatus }) {
  const className = "mt-0.5 size-4 shrink-0"
  if (status === "completed") {
    return (
      <Check
        aria-hidden="true"
        className={cn(className, "text-success-foreground")}
      />
    )
  }
  if (status === "in_progress") {
    return (
      <Loader2
        aria-hidden="true"
        className={cn(
          className,
          "animate-spin text-foreground motion-reduce:animate-none",
        )}
      />
    )
  }
  return (
    <Circle
      aria-hidden="true"
      className={cn(className, "text-muted-foreground/55")}
    />
  )
}
