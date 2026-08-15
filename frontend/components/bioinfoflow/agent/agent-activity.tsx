"use client"

import { useId, useMemo, useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Clock3,
  Loader2,
  TerminalSquare,
} from "@/lib/icons"
import { Button } from "@/components/ui/button"
import type {
  JsonValue,
  ToolExecutionMode,
  ToolProgressView,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type AgentToolCardProps = {
  tool: ToolProgressView
  defaultExpanded?: boolean
}

type AgentActivityGroupProps = {
  tools: ToolProgressView[]
  executionMode?: ToolExecutionMode
  defaultExpanded?: boolean
}

const durationNumberFormatters = new Map<string, Intl.NumberFormat>()

export function AgentToolCard({ tool, defaultExpanded }: AgentToolCardProps) {
  const t = useTranslations("agentActivity")
  const locale = useLocale()
  const detailsId = useId()
  const hasDetails = Boolean(
    hasDisplayValue(tool.arguments) ||
      tool.input_summary ||
      tool.output_summary ||
      tool.error,
  )
  const expansionKey = `${tool.call_id}:${tool.status}:${hasDetails}`
  const shouldExpand = defaultExpanded ?? false
  const [expansion, setExpansion] = useState({
    key: expansionKey,
    expanded: shouldExpand,
  })
  const expanded =
    expansion.key === expansionKey ? expansion.expanded : shouldExpand
  const duration = toolDuration(tool, locale)

  return (
    <article
      className={cn(
        "min-w-0 rounded-[10px] border border-border/70 bg-background",
        tool.status === "failed" && "border-error-border bg-error-muted/25",
        tool.status === "interaction_required" &&
          "border-warning-border bg-warning-muted/25",
      )}
      data-testid="agent-tool-card"
    >
      <div className="flex min-h-10 min-w-0 items-center gap-2 px-3 py-2 text-xs">
        <ToolStatusIcon status={tool.status} />
        <span
          className="min-w-0 max-w-[40%] truncate rounded-[5px] bg-muted/70 px-1.5 py-0.5 font-mono text-[11px] text-foreground/72"
          title={tool.display_name}
          translate="no"
        >
          {tool.display_name}
        </span>
        <span className="min-w-0 flex-1 truncate text-foreground/78">
          {tool.summary}
        </span>
        {duration ? (
          <span
            className="shrink-0 tabular-nums text-[11px] text-muted-foreground"
            translate="no"
          >
            {duration}
          </span>
        ) : null}
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {t(`status.${tool.status}`)}
        </span>
        {hasDetails ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="shrink-0 text-muted-foreground hover:text-foreground"
            aria-expanded={expanded}
            aria-controls={detailsId}
            aria-label={t(expanded ? "details.hide" : "details.show")}
            onClick={() =>
              setExpansion({ key: expansionKey, expanded: !expanded })
            }
          >
            {expanded ? (
              <ChevronDown aria-hidden="true" />
            ) : (
              <ChevronRight aria-hidden="true" />
            )}
          </Button>
        ) : null}
      </div>

      {hasDetails && expanded ? (
        <div
          id={detailsId}
          className="grid gap-3 border-t border-border/60 px-3 py-3"
        >
          {tool.input_summary ? (
            <ToolDetail label={t("details.input")} value={tool.input_summary} />
          ) : null}
          {hasDisplayValue(tool.arguments) ? (
            <ToolDetail
              label={t("details.arguments")}
              value={formatJsonValue(tool.arguments)}
              code
            />
          ) : null}
          {tool.output_summary ? (
            <ToolDetail
              label={t("details.output")}
              value={tool.output_summary}
              code
            />
          ) : null}
          {tool.error ? (
            <ToolDetail
              label={t("details.error")}
              value={publicErrorMessage(tool.error)}
              tone="error"
            />
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

export function AgentActivityGroup({
  tools,
  executionMode,
  defaultExpanded,
}: AgentActivityGroupProps) {
  const t = useTranslations("agentActivity")
  const detailsId = useId()
  const statusKey = tools.map((tool) => `${tool.call_id}:${tool.status}`).join("|")
  const shouldExpand =
    defaultExpanded ?? tools.some((tool) => toolNeedsAttention(tool.status))
  const [expansion, setExpansion] = useState({
    key: statusKey,
    expanded: shouldExpand,
  })
  const expanded = expansion.key === statusKey ? expansion.expanded : shouldExpand
  const resolvedExecutionMode =
    executionMode ?? commonExecutionMode(tools) ?? "mixed"
  const summaryKey = `group.${resolvedExecutionMode}`
  const groupedTools = useMemo(
    () => groupContiguousToolsByCategory(tools),
    [tools],
  )

  return (
    <section
      className="min-w-0 rounded-[10px] border border-border/70 bg-background"
      data-testid="agent-activity-group"
    >
      <button
        type="button"
        className="flex min-h-11 w-full min-w-0 items-center gap-2 rounded-[10px] px-3 py-2 text-left text-sm transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={t(summaryKey, { count: tools.length })}
        onClick={() => setExpansion({ key: statusKey, expanded: !expanded })}
      >
        <GroupStatusIcon tools={tools} />
        <span className="min-w-0 flex-1 truncate text-foreground/78">
          {t(summaryKey, { count: tools.length })}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {groupStatusLabel(t, tools)}
        </span>
        {expanded ? (
          <ChevronDown aria-hidden="true" />
        ) : (
          <ChevronRight aria-hidden="true" />
        )}
      </button>

      {expanded ? (
        <div
          id={detailsId}
          className="grid gap-3 border-t border-border/60 px-3 py-3"
        >
          {groupedTools.map(([category, categoryTools]) => (
            <div
              key={`${category}:${categoryTools[0]?.call_id}`}
              className="grid gap-2"
            >
              {groupedTools.length > 1 ? (
                <h3 className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
                  {t(`category.${category}`)}
                </h3>
              ) : null}
              {categoryTools.map((tool) => (
                <AgentToolCard key={tool.call_id} tool={tool} />
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
}: {
  label: string
  value: string
  code?: boolean
  tone?: "default" | "error"
}) {
  return (
    <div className="grid gap-1.5">
      <h4 className="text-[11px] font-medium text-muted-foreground">{label}</h4>
      <div
        className={cn(
          "max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-muted/45 px-2.5 py-2 text-xs leading-5 text-foreground/75",
          code && "font-mono",
          tone === "error" && "bg-error-muted/55 text-error-foreground",
        )}
      >
        {value}
      </div>
    </div>
  )
}

function ToolStatusIcon({ status }: { status: ToolProgressView["status"] }) {
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

function GroupStatusIcon({ tools }: { tools: ToolProgressView[] }) {
  if (tools.some((tool) => tool.status === "failed")) {
    return <AlertTriangle aria-hidden="true" className="size-4 shrink-0 text-error-foreground" />
  }
  if (tools.some((tool) => tool.status === "interaction_required" || tool.status === "blocked")) {
    return <CircleDashed aria-hidden="true" className="size-4 shrink-0 text-warning-foreground" />
  }
  if (tools.some((tool) => tool.status === "running")) {
    return <Loader2 aria-hidden="true" className="size-4 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" />
  }
  if (tools.every((tool) => tool.status === "completed")) {
    return <CheckCircle2 aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
  }
  return <CircleDashed aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
}

function groupStatusLabel(
  t: (key: string) => string,
  tools: ToolProgressView[],
) {
  if (tools.some((tool) => tool.status === "failed")) return t("status.failed")
  if (tools.some((tool) => tool.status === "interaction_required")) {
    return t("status.interaction_required")
  }
  if (tools.some((tool) => tool.status === "blocked")) return t("status.blocked")
  if (tools.some((tool) => tool.status === "running")) return t("status.running")
  if (tools.every((tool) => tool.status === "completed")) {
    return t("status.completed")
  }
  if (tools.every((tool) => tool.status === "cancelled")) {
    return t("status.cancelled")
  }
  return t("status.pending")
}

function groupContiguousToolsByCategory(tools: ToolProgressView[]) {
  const categories: Array<[ToolProgressView["category"], ToolProgressView[]]> = []
  for (const tool of tools) {
    const current = categories.at(-1)
    if (current?.[0] === tool.category) {
      current[1].push(tool)
    } else {
      categories.push([tool.category, [tool]])
    }
  }
  return categories
}

function commonExecutionMode(tools: ToolProgressView[]) {
  const first = tools[0]?.execution_mode
  if (!first) return null
  return tools.every((tool) => tool.execution_mode === first) ? first : null
}

function toolNeedsAttention(status: ToolProgressView["status"]) {
  return !["completed", "cancelled"].includes(status)
}

function toolDuration(tool: ToolProgressView, locale: string) {
  if (!tool.started_at || !tool.completed_at) return null
  const milliseconds =
    new Date(tool.completed_at).getTime() - new Date(tool.started_at).getTime()
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

function publicErrorMessage(error: ToolProgressView["error"]) {
  return error ?? ""
}

function hasDisplayValue(value: JsonValue) {
  if (value === null) return false
  if (typeof value === "string") return value.length > 0
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === "object") return Object.keys(value).length > 0
  return true
}

function formatJsonValue(value: JsonValue) {
  const formatted = JSON.stringify(value, null, 2)
  return formatted ?? String(value)
}
