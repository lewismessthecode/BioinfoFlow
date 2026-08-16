"use client"

import { useId } from "react"
import { useTranslations } from "next-intl"

import { useActivityDisclosure } from "@/components/bioinfoflow/agent/activity-disclosure"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { ChevronDown, ChevronRight, Loader2, Sparkles } from "@/lib/icons"
import type { ReasoningTranscriptBlock } from "@/lib/agent/conversation-model/types"

type AgentThinkingProps = {
  reasoning: ReasoningTranscriptBlock
  label?: string
}

export function AgentThinking({
  reasoning,
  label,
}: AgentThinkingProps) {
  const t = useTranslations("agentThinking")
  const detailsId = useId()
  const [expanded, setExpanded] = useActivityDisclosure(
    `thinking:${reasoning.id}`,
  )
  const text = reasoning.text.trim()
  const resolvedActive = reasoning.streaming
  const duration = !resolvedActive
    ? formatThinkingDuration(reasoning.durationMs)
    : null

  if (!text) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex min-h-9 min-w-0 items-center gap-2 text-xs text-muted-foreground"
        data-testid="agent-thinking"
      >
        <Loader2
          aria-hidden="true"
          className="size-4 shrink-0 animate-spin motion-reduce:animate-none"
        />
        <span>{resolvedActive ? t("running") : t("title")}</span>
      </div>
    )
  }

  return (
    <section
      aria-label={label ?? t("title")}
      className="min-w-0 text-muted-foreground"
      data-testid="agent-thinking"
    >
      <button
        type="button"
        className="group/summary flex min-h-9 w-full min-w-0 items-center gap-2 rounded-[6px] px-1 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/25 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 motion-reduce:transition-none"
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={`${label ?? t("title")}: ${firstLine(text)}. ${t(expanded ? "hide" : "show")}`}
        onClick={() => setExpanded((value) => !value)}
      >
        <Sparkles aria-hidden="true" className="size-4 shrink-0" />
        <span className="shrink-0 font-medium">{label ?? t("title")}</span>
        <span className="min-w-0 flex-1 truncate text-foreground/65">
          {firstLine(text)}
        </span>
        {duration ? (
          <span
            className="shrink-0 tabular-nums text-muted-foreground/75"
            data-testid="agent-thinking-duration"
            translate="no"
          >
            {t("duration", { duration })}
          </span>
        ) : null}
        {expanded ? (
          <ChevronDown aria-hidden="true" className="size-3.5 opacity-60 transition-opacity group-hover/summary:opacity-100" />
        ) : (
          <ChevronRight aria-hidden="true" className="size-3.5 opacity-60 transition-opacity group-hover/summary:opacity-100" />
        )}
      </button>

      {expanded ? (
        <div id={detailsId} className="ml-4 border-l border-border/50 pb-2 pl-3 pr-3 pt-1 text-foreground/72">
          <MarkdownRenderer content={text} variant="agent-transcript" />
        </div>
      ) : null}
    </section>
  )
}

function firstLine(text: string) {
  return text.split(/\r?\n/, 1)[0]
}

function formatThinkingDuration(durationMs: number | null) {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs < 0) {
    return null
  }
  const seconds = durationMs / 1000
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: seconds < 10 ? 1 : 0,
  }).format(seconds)
}
