"use client"

import { useTranslations } from "next-intl"

import { Check, ChevronDown, Circle, Loader2 } from "@/lib/icons"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import type { ConversationPlan } from "@/lib/agent/conversation-model/types"
import { cn } from "@/lib/utils"

export function AgentPlanCard({
  plan,
  className,
}: {
  plan: ConversationPlan
  className?: string
}) {
  const t = useTranslations("agentHistory")
  const total = plan.items.length
  const completed = plan.items.filter(
    (item) => item.status === "completed",
  ).length

  const currentIndex = plan.items.findIndex(
    (item) => item.status === "in_progress",
  )
  const step = currentIndex >= 0 ? currentIndex + 1 : Math.min(completed + 1, total)

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "group flex h-9 max-w-full items-center gap-2 rounded-full border border-border/60 bg-background/95 px-3 text-sm text-muted-foreground shadow-sm shadow-foreground/[0.03] backdrop-blur-md transition-colors hover:border-border hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
            className,
          )}
          aria-label={t("plan.expand")}
          data-testid="agent-plan-trigger"
        >
          <PlanStatusIcon
            status={completed === total ? "completed" : "in_progress"}
            active={plan.active}
          />
          <span className="truncate tabular-nums">
            {t("plan.step_progress", { step, total })}
          </span>
          <ChevronDown
            aria-hidden="true"
            className="size-3.5 transition-transform group-data-[state=open]:rotate-180"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="center"
        sideOffset={10}
        className="w-[min(36rem,calc(100vw-2rem))] rounded-2xl border-border/60 bg-background/98 p-3 shadow-xl shadow-foreground/[0.08] backdrop-blur-xl"
        data-testid="agent-plan-card"
      >
        <div className="flex min-w-0 items-center justify-between gap-3 px-1 pb-2">
          <h2 className="truncate text-sm font-medium text-foreground">
            {plan.title ?? t("plan.title")}
          </h2>
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {t("plan.progress", { completed, total })}
          </span>
        </div>
        <ol className="grid gap-0.5">
          {plan.items.map((item) => (
            <li
              key={item.id}
              className="flex min-w-0 items-start gap-2.5 rounded-xl px-2 py-2 text-sm"
            >
              <PlanStatusIcon status={item.status} active={plan.active} />
              <span
                className={cn(
                  "min-w-0 flex-1 break-words leading-5",
                  item.status === "completed" && "text-muted-foreground",
                  item.status === "in_progress" && "font-medium text-foreground",
                  item.status === "pending" && "text-foreground/68",
                )}
              >
                {item.text}
              </span>
            </li>
          ))}
        </ol>
      </PopoverContent>
    </Popover>
  )
}

function PlanStatusIcon({
  status,
  active,
}: {
  status: ConversationPlan["items"][number]["status"]
  active: boolean
}) {
  const className = "mt-0.5 size-4 shrink-0"
  if (status === "completed") {
    return (
      <Check
        aria-hidden="true"
        className={cn(className, "text-success-foreground")}
      />
    )
  }
  if (status === "in_progress" && active) {
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
