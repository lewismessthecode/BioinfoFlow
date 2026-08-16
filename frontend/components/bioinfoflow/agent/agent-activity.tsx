"use client"

import { useId, useMemo, useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import { useActivityDisclosure } from "@/components/bioinfoflow/agent/activity-disclosure"
import { Button } from "@/components/ui/button"
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Clock3,
  Copy,
  Loader2,
  TerminalSquare,
} from "@/lib/icons"
import type {
  ActivityGroupTranscriptBlock,
  ActivityItem,
} from "@/lib/agent/conversation-model/types"
import { cn } from "@/lib/utils"

type AgentToolCardProps = {
  activity: ActivityItem
  defaultExpanded?: boolean
  grouped?: boolean
}

type AgentActivityGroupProps = {
  activityGroup: ActivityGroupTranscriptBlock
  defaultExpanded?: boolean
}

const durationNumberFormatters = new Map<string, Intl.NumberFormat>()

export function AgentToolCard({
  activity,
  defaultExpanded,
  grouped = false,
}: AgentToolCardProps) {
  const t = useTranslations("agentActivity")
  const locale = useLocale()
  const detailsId = useId()
  const details = activity.details ?? publicActivityDetails(activity)
  const hasDetails = details.length > 0
  const [expanded, setExpanded] = useActivityDisclosure(
    `tool:${activity.callId}`,
    defaultExpanded ?? false,
  )
  const duration = activityDuration(activity, locale)
  const summary = (
    <>
      <ToolStatusIcon status={activity.status} />
      <span
        className="min-w-0 max-w-[34%] truncate rounded-[5px] bg-muted/70 px-1.5 py-0.5 font-mono text-[11px] text-foreground/72 sm:max-w-[40%]"
        title={activity.displayName}
        translate="no"
      >
        {activity.displayName}
      </span>
      <span className="line-clamp-2 min-w-0 flex-1 text-foreground/78 sm:truncate">
        {activity.summary}
      </span>
      {duration ? (
        <span
          className="hidden shrink-0 tabular-nums text-[11px] text-muted-foreground sm:inline"
          translate="no"
        >
          {duration}
        </span>
      ) : null}
      <span className="sr-only shrink-0 text-[11px] text-muted-foreground sm:not-sr-only">
        {t(`status.${activity.status}`)}
      </span>
      {hasDetails ? (
        expanded ? (
          <ChevronDown aria-hidden="true" />
        ) : (
          <ChevronRight aria-hidden="true" />
        )
      ) : null}
    </>
  )

  return (
    <article
      className={cn(
        "min-w-0",
        !grouped && "rounded-[10px] border border-border/60 bg-background",
        grouped && "bg-transparent",
        activity.status === "failed" && !grouped && "border-error-border bg-error-muted/25",
        activity.status === "interaction_required" &&
          !grouped &&
          "border-warning-border bg-warning-muted/25",
      )}
      data-grouped={grouped ? "true" : undefined}
      data-testid="agent-tool-card"
    >
      {hasDetails ? (
        <button
          type="button"
          className={cn(
            "flex h-9 w-full min-w-0 items-center gap-2 rounded-[10px] px-3 py-1 text-left text-xs transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 motion-reduce:transition-none",
            grouped && "rounded-[6px] px-1.5",
          )}
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`${activity.displayName}: ${activity.summary}. ${t(expanded ? "details.hide" : "details.show")}`}
          onClick={() => setExpanded((value) => !value)}
        >
          {summary}
        </button>
      ) : (
        <div
          className={cn(
            "flex h-9 min-w-0 items-center gap-2 px-3 py-1 text-xs",
            grouped && "px-1.5",
          )}
        >
          {summary}
        </div>
      )}

      {hasDetails && expanded ? (
        <div
          id={detailsId}
          className={cn(
            "grid gap-3 border-l border-border/50 py-2 pl-4 pr-3",
            grouped && "ml-4 pr-2",
            !grouped && "mx-3 mb-3",
          )}
        >
          {details.map((detail) => (
            <ToolDetail
              key={detail.id}
              label={detail.label ?? t(`details.${detail.kind}`)}
              value={detail.value}
              code={detail.format !== "text"}
              tone={detail.kind === "error" ? "error" : "default"}
              note={[
                detail.redacted ? t("details.redacted") : null,
                detail.truncated ? t("details.truncated") : null,
              ]
                .filter(Boolean)
                .join(" · ")}
              copyable={detail.copyable}
            />
          ))}
        </div>
      ) : null}
    </article>
  )
}

export function AgentActivityGroup({
  activityGroup,
  defaultExpanded,
}: AgentActivityGroupProps) {
  const activities = activityGroup.activities
  const t = useTranslations("agentActivity")
  const detailsId = useId()
  const disclosureKey = useMemo(
    () => `tool-group:${activities.map((activity) => activity.callId).join("|")}`,
    [activities],
  )
  const [expanded, setExpanded] = useActivityDisclosure(
    disclosureKey,
    defaultExpanded ?? false,
  )
  const summaryKey = `group.${activityGroup.executionMode}`
  const groupedActivities = useMemo(
    () => groupContiguousActivitiesByCategory(activities),
    [activities],
  )

  return (
    <section
      className="min-w-0"
      data-testid="agent-activity-group"
    >
      <button
        type="button"
        className="group/summary flex h-9 w-full min-w-0 items-center gap-1.5 rounded-[6px] px-1 py-1 text-left text-xs transition-colors hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 motion-reduce:transition-none"
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={t(summaryKey, { count: activities.length })}
        onClick={() => setExpanded((value) => !value)}
      >
        <GroupStatusIcon activities={activities} />
        <span className="min-w-0 flex-1 truncate text-foreground/78">
          {t(summaryKey, { count: activities.length })}
        </span>
        <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
          {groupStatusLabel(t, activities)}
        </span>
        {expanded ? (
          <ChevronDown aria-hidden="true" className="size-3.5 opacity-60 transition-opacity group-hover/summary:opacity-100" />
        ) : (
          <ChevronRight aria-hidden="true" className="size-3.5 opacity-60 transition-opacity group-hover/summary:opacity-100" />
        )}
      </button>

      {expanded ? (
        <div
          id={detailsId}
          className="ml-3 grid gap-2 border-l border-border/55 py-1.5 pl-3"
        >
          {groupedActivities.map(([category, categoryActivities]) => (
            <div
              key={`${category}:${categoryActivities[0]?.callId}`}
              className="grid gap-2"
            >
              {groupedActivities.length > 1 ? (
                <h3 className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                  {t(`category.${category}`)}
                </h3>
              ) : null}
              {categoryActivities.map((activity) => (
                <AgentToolCard key={activity.callId} activity={activity} grouped />
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

function ToolDetail({
  label,
  value,
  code = false,
  tone = "default",
  note,
  copyable = false,
}: {
  label: string
  value: string
  code?: boolean
  tone?: "default" | "error"
  note?: string
  copyable?: boolean
}) {
  const t = useTranslations("agentActivity")
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  )

  async function copyDetail() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(value)
      setCopyState("copied")
    } catch {
      setCopyState("failed")
    }
  }

  return (
    <div className="grid gap-1.5">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <h4 className="min-w-0 text-[11px] font-medium text-muted-foreground">
          {label}
        </h4>
        {copyable ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="shrink-0 text-muted-foreground hover:text-foreground"
            aria-label={t(
              copyState === "copied" ? "details.copied" : "details.copy",
              { label },
            )}
            onClick={() => void copyDetail()}
          >
            {copyState === "copied" ? (
              <Check aria-hidden="true" />
            ) : (
              <Copy aria-hidden="true" />
            )}
          </Button>
        ) : null}
      </div>
      <div
        className={cn(
          "max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-muted/45 px-2.5 py-2 text-xs leading-5 text-foreground/75",
          code && "font-mono",
          tone === "error" && "bg-error-muted/55 text-error-foreground",
        )}
      >
        {value}
      </div>
      {note ? <p className="text-[11px] text-muted-foreground">{note}</p> : null}
      {copyState === "failed" ? (
        <p
          role="alert"
          aria-live="polite"
          className="text-[11px] text-error-foreground"
        >
          {t("details.copy_failed")}
        </p>
      ) : null}
    </div>
  )
}

function ToolStatusIcon({ status }: { status: ActivityStatus }) {
  const className = "size-4 shrink-0 text-muted-foreground"
  if (status === "running") {
    return <Loader2 aria-hidden="true" className={cn(className, "animate-spin motion-reduce:animate-none")} />
  }
  if (status === "completed") {
    return <CheckCircle2 aria-hidden="true" className={className} />
  }
  if (status === "failed") {
    return <AlertTriangle aria-hidden="true" className="size-4 shrink-0 text-error-foreground" />
  }
  if (status === "blocked" || status === "interaction_required") {
    return <CircleDashed aria-hidden="true" className="size-4 shrink-0 text-warning-foreground" />
  }
  if (status === "cancelled") {
    return <TerminalSquare aria-hidden="true" className={className} />
  }
  return <Clock3 aria-hidden="true" className={className} />
}

function GroupStatusIcon({ activities }: { activities: ActivityItem[] }) {
  if (activities.some((activity) => activity.status === "failed")) {
    return <AlertTriangle aria-hidden="true" className="size-4 shrink-0 text-error-foreground" />
  }
  if (activities.some((activity) => activity.status === "interaction_required" || activity.status === "blocked")) {
    return <CircleDashed aria-hidden="true" className="size-4 shrink-0 text-warning-foreground" />
  }
  if (activities.some((activity) => activity.status === "running")) {
    return <Loader2 aria-hidden="true" className="size-4 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" />
  }
  if (activities.every((activity) => activity.status === "completed")) {
    return <CheckCircle2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
  }
  return <CircleDashed aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
}

function groupStatusLabel(
  t: (key: string) => string,
  activities: ActivityItem[],
) {
  if (activities.some((activity) => activity.status === "failed")) return t("status.failed")
  if (activities.some((activity) => activity.status === "interaction_required")) {
    return t("status.interaction_required")
  }
  if (activities.some((activity) => activity.status === "blocked")) return t("status.blocked")
  if (activities.some((activity) => activity.status === "running")) return t("status.running")
  if (activities.every((activity) => activity.status === "completed")) {
    return t("status.completed")
  }
  if (activities.every((activity) => activity.status === "cancelled")) {
    return t("status.cancelled")
  }
  return t("status.pending")
}

function groupContiguousActivitiesByCategory(activities: ActivityItem[]) {
  const categories: Array<[string, ActivityItem[]]> = []
  for (const activity of activities) {
    const category = activityCategory(activity.category)
    const current = categories.at(-1)
    if (current?.[0] === category) {
      current[1].push(activity)
    } else {
      categories.push([category, [activity]])
    }
  }
  return categories
}

function activityDuration(activity: ActivityItem, locale: string) {
  if (!activity.startedAt || !activity.completedAt) return null
  const milliseconds =
    new Date(activity.completedAt).getTime() - new Date(activity.startedAt).getTime()
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return null
  const number = durationNumberFormatter(locale)
  if (milliseconds < 1000) return `${number.format(milliseconds)} ms`
  if (milliseconds < 60_000) {
    return `${number.format(milliseconds / 1000)} s`
  }
  const totalSeconds = Math.round(milliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${number.format(minutes)}m ${number.format(seconds)}s`
}

function durationNumberFormatter(locale: string) {
  const cached = durationNumberFormatters.get(locale)
  if (cached) return cached
  const formatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 })
  durationNumberFormatters.set(locale, formatter)
  return formatter
}

function activityCategory(value: string) {
  return [
    "read",
    "search",
    "command",
    "edit",
    "write",
    "workflow",
    "plan",
    "interaction",
    "other",
  ].includes(value)
    ? value
    : "other"
}

function publicActivityDetails(activity: ActivityItem) {
  return [
    publicActivityDetail(activity, "input", activity.input, "json"),
    publicActivityDetail(activity, "output", activity.output, "text"),
    publicActivityDetail(activity, "error", activity.error, "text"),
  ].filter((detail) => detail !== null)
}

function publicActivityDetail(
  activity: ActivityItem,
  kind: "input" | "output" | "error",
  value: unknown,
  format: "json" | "text",
) {
  if (value === null || value === undefined) return null
  let text: string
  if (typeof value === "string") {
    text = value
  } else {
    try {
      text = JSON.stringify(value, null, 2)
    } catch {
      text = String(value)
    }
  }
  return {
    id: `${activity.id}:${kind}`,
    kind,
    label: null,
    value: text,
    format,
    copyable: true,
    truncated: false,
    redacted: false,
  }
}
