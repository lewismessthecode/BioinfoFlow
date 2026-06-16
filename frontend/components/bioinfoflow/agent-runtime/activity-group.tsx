"use client"

import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeActivityGroup } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ToolActivityRow } from "./tool-activity-row"

export function ActivityGroup({ group }: { group: AgentRuntimeActivityGroup }) {
  const t = useTranslations("agentRuntime")
  const expansionKey = `${group.id}:${group.status}`
  const defaultExpanded = false
  const [expansion, setExpansion] = useState({
    key: expansionKey,
    expanded: defaultExpanded,
  })
  const expanded =
    expansion.key === expansionKey ? expansion.expanded : defaultExpanded

  return (
    <div className="my-1 text-muted-foreground" data-testid="agent-activity-group">
      <button
        type="button"
        className={cn(
          "flex w-full items-center gap-2 rounded-xl bg-muted/35 px-3 py-2 text-left text-xs transition-colors hover:bg-muted/55",
          group.status === "failed" || group.status === "cancelled" || group.status === "rejected"
            ? "text-amber-700 dark:text-amber-300"
            : "text-muted-foreground",
        )}
        onClick={() =>
          setExpansion({
            key: expansionKey,
            expanded: !expanded,
          })
        }
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
        )}
        <span className="font-medium text-foreground/75">
          {t(`activity.groups.${group.kind}`)}
        </span>
        <span className="min-w-0 flex-1 truncate">{activitySummary(t, group)}</span>
        {group.status !== "completed" ? (
          <span
            className={cn(
              "shrink-0 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide",
              group.status === "failed" || group.status === "cancelled" || group.status === "rejected"
                ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                : "bg-background/70 text-muted-foreground",
            )}
          >
            {t(`activity.status.${group.status}`)}
          </span>
        ) : null}
      </button>

      {expanded ? (
        <div className="mt-2 grid gap-3 pl-4">
          {group.activities.map((activity) => (
            <ToolActivityRow key={activity.id} activity={activity} />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function activitySummary(
  t: (key: string, values?: Record<string, number>) => string,
  group: AgentRuntimeActivityGroup,
) {
  return t(`activity.summary.${group.kind}`, { count: group.activities.length })
}
