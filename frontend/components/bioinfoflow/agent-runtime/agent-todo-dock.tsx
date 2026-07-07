"use client"

import { useMemo, useState } from "react"
import { ChevronDown, ChevronUp, ListChecks } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentTodoDisplayItem } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { TodoChecklist } from "./todo-checklist"

export function AgentTodoDock({ items }: { items: AgentTodoDisplayItem[] }) {
  const t = useTranslations("agentRuntime")
  const [expanded, setExpanded] = useState(true)
  const active = useMemo(
    () => items.find((item) => item.displayStatus === "in_progress") ?? null,
    [items],
  )
  const incompleteCount = items.filter((item) => item.displayStatus !== "completed").length

  if (!items.length) return null

  return (
    <section
      className={cn(
        "absolute right-4 top-4 z-20 w-[min(360px,calc(100%-32px))] rounded-[12px] border border-border/70 bg-card shadow-[0_10px_28px_rgba(36,35,33,0.07)] transition-all",
        !expanded && "w-[min(280px,calc(100%-32px))]",
      )}
      data-testid="agent-todo-dock"
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        aria-label={expanded ? t("todoDock.collapse") : t("todoDock.expand")}
      >
        <ListChecks className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-medium text-foreground">
          {expanded
            ? t("progress.tasks")
            : active?.activeForm || active?.content || t("todoDock.summary", { count: incompleteCount })}
        </span>
        <span className="rounded-[6px] bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
          {items.filter((item) => item.displayStatus === "completed").length}/{items.length}
        </span>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {expanded ? (
        <div className="max-h-[min(420px,calc(100vh-220px))] overflow-y-auto border-t border-border/60 px-3 py-3">
          <TodoChecklist todos={items} compact />
        </div>
      ) : null}
    </section>
  )
}
