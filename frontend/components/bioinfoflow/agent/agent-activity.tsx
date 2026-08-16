"use client"

import { useId, useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import { useActivityDisclosure } from "@/components/bioinfoflow/agent/activity-disclosure"
import { Button } from "@/components/ui/button"
import {
  Activity as ActivityGlyph,
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDashed,
  Copy,
  FileText,
  ListChecks,
  Loader2,
  MessageSquare,
  Pencil,
  Play,
  Search,
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
  const description = activityDescription(activity)
  const visibleDescription =
    activity.status === "failed" && activity.error
      ? activity.error
      : description
  const summary = (
    <>
      <ToolActivityIcon activity={activity} />
      <span
        className="min-w-0 max-w-[34%] shrink-0 truncate font-medium text-foreground/76 sm:max-w-[40%]"
        data-activity-label=""
        title={activity.displayName}
        translate="no"
      >
        {activity.displayName}
      </span>
      {visibleDescription ? (
        <>
          <span aria-hidden="true" className="shrink-0 text-muted-foreground/45">
            ·
          </span>
          <span
            className={cn(
              "min-w-0 flex-1 truncate text-foreground/68",
              activity.status === "failed" && "text-error-foreground",
            )}
          >
            {visibleDescription}
          </span>
        </>
      ) : (
        <span className="min-w-0 flex-1" />
      )}
      {duration ? (
        <span
          className="hidden shrink-0 tabular-nums text-[11px] text-muted-foreground sm:inline"
          translate="no"
        >
          {duration}
        </span>
      ) : null}
      <span className="sr-only">
        {t(`status.${activity.status}`)}
      </span>
      {hasDetails ? (
        expanded ? (
          <ChevronDown
            aria-hidden="true"
            className="size-3.5 shrink-0 opacity-45 transition-opacity group-hover/activity:opacity-75 group-focus-within/activity:opacity-75"
          />
        ) : (
          <ChevronRight
            aria-hidden="true"
            className="size-3.5 shrink-0 opacity-45 transition-opacity group-hover/activity:opacity-75 group-focus-within/activity:opacity-75"
          />
        )
      ) : null}
    </>
  )

  return (
    <article
      className={cn(
        "group/activity min-w-0",
        grouped && "bg-transparent",
      )}
      data-activity-category={activity.category}
      data-activity-status={activity.status}
      data-agent-activity-row=""
      data-call-id={activity.callId}
      data-grouped={grouped ? "true" : undefined}
      data-testid="agent-tool-card"
    >
      {hasDetails ? (
        <button
          type="button"
          className={cn(
            "flex min-h-8 w-full min-w-0 items-center gap-1.5 rounded-[6px] px-1 py-1 text-left text-[13px] leading-5 transition-colors hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 motion-reduce:transition-none",
          )}
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`${activity.displayName}${visibleDescription ? `: ${visibleDescription}` : ""}. ${t(expanded ? "details.hide" : "details.show")}`}
          onClick={() => setExpanded((value) => !value)}
        >
          {summary}
        </button>
      ) : (
        <div
          className={cn(
            "flex min-h-8 min-w-0 items-center gap-1.5 px-1 py-1 text-[13px] leading-5",
          )}
        >
          {summary}
        </div>
      )}

      {hasDetails && expanded ? (
        <div
          id={detailsId}
          className="ml-5 grid gap-3 border-l border-border/50 py-2 pl-3 pr-2"
          data-activity-detail=""
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

  return (
    <section
      className="grid min-w-0 gap-1"
      data-execution-mode={activityGroup.executionMode}
      data-testid="agent-activity-group"
    >
      {activities.map((activity) => (
        <AgentToolCard
          key={activity.callId}
          activity={activity}
          defaultExpanded={defaultExpanded}
          grouped
        />
      ))}
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

function ToolActivityIcon({ activity }: { activity: ActivityItem }) {
  const className = "size-4 shrink-0 text-muted-foreground/72"
  if (activity.status === "running") {
    return (
      <Loader2
        aria-hidden="true"
        className={cn(className, "animate-spin motion-reduce:animate-none")}
      />
    )
  }
  if (activity.status === "failed") {
    return (
      <span className="flex size-4 shrink-0 items-center justify-center">
        <Circle
          aria-hidden="true"
          className="size-2.5 fill-current text-error-foreground"
        />
      </span>
    )
  }
  if (
    activity.status === "blocked" ||
    activity.status === "interaction_required" ||
    activity.status === "cancelled"
  ) {
    return (
      <CircleDashed
        aria-hidden="true"
        className={cn(
          className,
          activity.status !== "cancelled" && "text-warning-foreground",
        )}
      />
    )
  }

  return (
    <ActivityCategoryIcon
      category={activity.category}
      className={className}
    />
  )
}

function ActivityCategoryIcon({
  category,
  className,
}: {
  category: string
  className: string
}) {
  if (category === "command") {
    return <TerminalSquare aria-hidden="true" className={className} />
  }
  if (category === "read") {
    return <FileText aria-hidden="true" className={className} />
  }
  if (category === "search") {
    return <Search aria-hidden="true" className={className} />
  }
  if (category === "edit" || category === "write") {
    return <Pencil aria-hidden="true" className={className} />
  }
  if (category === "workflow") {
    return <Play aria-hidden="true" className={className} />
  }
  if (category === "plan") {
    return <ListChecks aria-hidden="true" className={className} />
  }
  if (category === "interaction") {
    return <MessageSquare aria-hidden="true" className={className} />
  }
  return <ActivityGlyph aria-hidden="true" className={className} />
}

function activityDescription(activity: ActivityItem) {
  const summary = activity.summary.trim()
  const labels = [activity.displayName, activity.name]
    .map((label) => label.trim())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)

  let description = summary
  for (const label of labels) {
    const prefix = new RegExp(
      `^${escapeRegExp(label)}(?:\\s*[:·—–-]\\s*|\\s+)`,
      "i",
    )
    if (!prefix.test(description)) continue
    description = description.replace(prefix, "").trim()
    break
  }
  if (description && !labels.some((label) => label.toLowerCase() === description.toLowerCase())) {
    return description
  }

  const primaryDetail = activity.details?.find((detail) =>
    ["command", "path", "working_directory"].includes(detail.kind),
  )
  return primaryDetail?.value.trim() || null
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
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
