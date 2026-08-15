"use client"

import { useId, useState } from "react"
import { useTranslations } from "next-intl"

import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { ChevronDown, ChevronRight, Loader2, Sparkles } from "@/lib/icons"
import type { AssistantDraftPartView } from "@/lib/agent/contracts"

type AgentThinkingProps = {
  part: Pick<AssistantDraftPartView, "id" | "type" | "text">
  active?: boolean
  label?: string
}

export function AgentThinking({
  part,
  active = false,
  label,
}: AgentThinkingProps) {
  const t = useTranslations("agentThinking")
  const detailsId = useId()
  const [expanded, setExpanded] = useState(false)
  const text = part.text.trim()

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
        <span>{active ? t("running") : t("title")}</span>
      </div>
    )
  }

  return (
    <section
      aria-label={label ?? t("title")}
      className="min-w-0 border-l border-border/60 pl-3"
      data-testid="agent-thinking"
    >
      <button
        type="button"
          className="flex min-h-11 w-full min-w-0 items-center gap-2 rounded-[6px] py-1.5 pr-2 text-left text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 motion-reduce:transition-none"
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={t(expanded ? "hide" : "show")}
        onClick={() => setExpanded((value) => !value)}
      >
        <Sparkles aria-hidden="true" className="size-4 shrink-0" />
        <span className="shrink-0 font-medium">{label ?? t("title")}</span>
        <span className="min-w-0 flex-1 truncate text-foreground/65">
          {firstLine(text)}
        </span>
        {expanded ? (
          <ChevronDown aria-hidden="true" />
        ) : (
          <ChevronRight aria-hidden="true" />
        )}
      </button>

      {expanded ? (
        <div id={detailsId} className="pb-2 pl-6 pr-3 pt-1 text-foreground/72">
          <MarkdownRenderer content={text} />
        </div>
      ) : null}
    </section>
  )
}

function firstLine(text: string) {
  return text.split(/\r?\n/, 1)[0]
}
