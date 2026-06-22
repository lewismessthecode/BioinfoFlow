"use client"

import { useId, useState } from "react"
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  FileText,
  Globe2,
  Loader2,
  PencilLine,
  Play,
  TerminalSquare,
  Wrench,
} from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeActivityGroup } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ToolActivityRow } from "./tool-activity-row"

export function ActivityGroup({ group }: { group: AgentRuntimeActivityGroup }) {
  const t = useTranslations("agentRuntime")
  const detailsId = useId()
  const expansionKey = `${group.id}:${group.status}`
  const defaultExpanded = ["building", "requested", "waiting", "running"].includes(group.status)
  const [expansion, setExpansion] = useState({
    key: expansionKey,
    expanded: defaultExpanded,
  })
  const expanded =
    expansion.key === expansionKey ? expansion.expanded : defaultExpanded

  return (
    <div className="my-0 text-muted-foreground" data-testid="agent-activity-group">
      <button
        type="button"
        className={cn(
          "flex min-h-6 w-full items-center gap-2 rounded-md px-1 py-0.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/25",
          group.status !== "completed" && "text-foreground/60",
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring",
        )}
        onClick={() =>
          setExpansion({
            key: expansionKey,
            expanded: !expanded,
          })
        }
        aria-expanded={expanded}
        aria-controls={expanded ? detailsId : undefined}
      >
        <ActivityIcon group={group} />
        <span className="min-w-0 flex-1 truncate">
          {activitySummary(t, group)}
        </span>
        {group.status !== "completed" ? (
          <span className="shrink-0 text-[11px] text-muted-foreground/80">
            {t(`activity.status.${group.status}`)}
          </span>
        ) : null}
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
        )}
      </button>

      {expanded ? (
        <div id={detailsId} className="ml-4 mt-1 grid gap-1 border-l border-border/50 pl-3">
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
  const count =
    group.kind === "search"
      ? group.activities.reduce(
          (total, activity) =>
            total + (activity.sourceResultCount ?? activity.sources.length),
          0,
        )
      : group.activities.length
  if (
    group.kind === "search" &&
    group.status !== "completed" &&
    group.activities.some(
      (activity) => activity.sourceResultCount === null || activity.sourceResultCount === undefined,
    )
  ) {
    return t("activity.summary.searching")
  }
  return t(`activity.summary.${group.kind}`, { count })
}

function ActivityIcon({ group }: { group: AgentRuntimeActivityGroup }) {
  const className = "h-3.5 w-3.5 shrink-0 text-muted-foreground/75"
  if (group.status === "running" || group.status === "building") {
    return <Loader2 className={cn(className, "animate-spin")} />
  }
  if (group.status === "waiting" || group.status === "requested") {
    return <CircleDashed className={className} />
  }
  if (group.status === "completed") {
    if (group.kind === "search") return <Globe2 className={className} />
    if (group.kind === "read") return <FileText className={className} />
    if (group.kind === "write" || group.kind === "register") {
      return <PencilLine className={className} />
    }
    if (group.kind === "run" || group.kind === "verify") return <Play className={className} />
    if (group.kind === "command") return <TerminalSquare className={className} />
    return <CheckCircle2 className={className} />
  }
  return <Wrench className={className} />
}
