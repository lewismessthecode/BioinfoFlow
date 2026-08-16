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
  ToolExecutionMode,
  ToolProgressView,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type AgentToolCardProps = {
  tool: ToolProgressView
  defaultExpanded?: boolean
  grouped?: boolean
}

type AgentActivityGroupProps = {
  tools: ToolProgressView[]
  executionMode?: ToolExecutionMode
  defaultExpanded?: boolean
}

const durationNumberFormatters = new Map<string, Intl.NumberFormat>()

export function AgentToolCard({
  tool,
  defaultExpanded,
  grouped = false,
}: AgentToolCardProps) {
  const t = useTranslations("agentActivity")
  const locale = useLocale()
  const detailsId = useId()
  const details = tool.public_details ?? []
  const hasDetails = details.length > 0
  const [expanded, setExpanded] = useActivityDisclosure(
    `tool:${tool.call_id}`,
    defaultExpanded ?? false,
  )
  const duration = toolDuration(tool, locale)
  const summary = (
    <>
      <ToolStatusIcon status={tool.status} />
      <span
        className="min-w-0 max-w-[34%] truncate rounded-[5px] bg-muted/70 px-1.5 py-0.5 font-mono text-[11px] text-foreground/72 sm:max-w-[40%]"
        title={tool.display_name}
        translate="no"
      >
        {tool.display_name}
      </span>
      <span className="line-clamp-2 min-w-0 flex-1 text-foreground/78 sm:truncate">
        {tool.summary}
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
        {t(`status.${tool.status}`)}
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
        tool.status === "failed" && !grouped && "border-error-border bg-error-muted/25",
        tool.status === "interaction_required" &&
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
            "flex min-h-11 w-full min-w-0 items-center gap-2 rounded-[10px] px-3 py-2 text-left text-xs transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 motion-reduce:transition-none",
            grouped && "rounded-[6px] px-2",
          )}
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`${tool.display_name}: ${tool.summary}. ${t(expanded ? "details.hide" : "details.show")}`}
          onClick={() => setExpanded((value) => !value)}
        >
          {summary}
        </button>
      ) : (
        <div
          className={cn(
            "flex min-h-11 min-w-0 items-center gap-2 px-3 py-2 text-xs",
            grouped && "px-2",
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
  tools,
  executionMode,
  defaultExpanded,
}: AgentActivityGroupProps) {
  const t = useTranslations("agentActivity")
  const detailsId = useId()
  const disclosureKey = useMemo(
    () => `tool-group:${tools.map((tool) => tool.call_id).join("|")}`,
    [tools],
  )
  const [expanded, setExpanded] = useActivityDisclosure(
    disclosureKey,
    defaultExpanded ?? tools.some((tool) => isActive(tool.status)),
  )
  const resolvedExecutionMode =
    executionMode ?? commonExecutionMode(tools) ?? "mixed"
  const summaryKey = `group.${resolvedExecutionMode}`
  const groupedTools = useMemo(
    () => groupContiguousToolsByCategory(tools),
    [tools],
  )

  return (
    <section
      className="min-w-0"
      data-testid="agent-activity-group"
    >
      <button
        type="button"
        className="group/summary flex min-h-9 w-full min-w-0 items-center gap-2 rounded-[6px] px-1 py-1.5 text-left text-xs transition-colors hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 motion-reduce:transition-none"
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={t(summaryKey, { count: tools.length })}
        onClick={() => setExpanded((value) => !value)}
      >
        <GroupStatusIcon tools={tools} />
        <span className="min-w-0 flex-1 truncate text-foreground/78">
          {t(summaryKey, { count: tools.length })}
        </span>
        <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
          {groupStatusLabel(t, tools)}
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
          className="ml-3 grid gap-3 border-l border-border/55 py-2 pl-3"
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
                <AgentToolCard key={tool.call_id} tool={tool} grouped />
              ))}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

function isActive(status: ToolProgressView["status"]) {
  return ["pending", "running", "blocked", "interaction_required"].includes(
    status,
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
