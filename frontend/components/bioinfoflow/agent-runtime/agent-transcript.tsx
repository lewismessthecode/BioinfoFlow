"use client"

import { useState } from "react"
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, CircleDashed, Wrench } from "lucide-react"
import { useTranslations } from "next-intl"

import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type {
  AgentRuntimeTimelineEntry,
  AgentRuntimeToolCallState,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function AgentTranscript({ timeline }: { timeline: AgentRuntimeTimelineEntry[] }) {
  const t = useTranslations("agentRuntime")

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-36 pt-8 sm:px-6">
      <div className="mx-auto grid w-full max-w-3xl gap-8">
        {timeline.map((entry) => (
          <article key={entry.turn.id} className="grid gap-4">
            <div className="flex justify-end">
              <div className="max-w-[82%] rounded-[22px] bg-muted px-4 py-3 text-[15px] leading-6 text-foreground">
                {entry.turn.input_text}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="w-full max-w-[88%] px-1">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                  <TurnStatusIcon status={entry.turn.status} />
                  <span>{turnStatusLabel(t, entry.turn.status)}</span>
                </div>

                {entry.assistant.thinking?.content ? (
                  <details className="mb-3 rounded-2xl border border-border/70 bg-muted/30 px-3 py-2">
                    <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-foreground">
                      <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
                      <span>{t("thinking")}</span>
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                      {entry.assistant.thinking.content}
                    </p>
                  </details>
                ) : null}

                {entry.assistant.toolCalls.length > 0 ? (
                  <div className="mb-3 overflow-hidden rounded-lg border border-border/60 bg-muted/20">
                    <div className="flex items-center gap-2 border-b border-border/50 px-2.5 py-1.5 text-xs font-medium text-muted-foreground">
                      <Wrench className="h-3.5 w-3.5" />
                      <span>{t("toolCalls")}</span>
                    </div>
                    {entry.assistant.toolCalls.map((toolCall) => (
                      <ToolCallRow
                        key={toolCall.callId}
                        toolCall={toolCall}
                      />
                    ))}
                  </div>
                ) : null}

                <MarkdownRenderer
                  className={cn(
                    "text-[15px] leading-7",
                    entry.assistant.status === "failed" &&
                      "[&_a]:text-destructive [&_code]:text-destructive [&_em]:text-destructive [&_h1]:text-destructive [&_h2]:text-destructive [&_h3]:text-destructive [&_h4]:text-destructive [&_li]:text-destructive [&_p]:text-destructive [&_strong]:text-destructive text-destructive",
                  )}
                  content={
                    entry.assistant.text ||
                    entry.assistant.errorMessage ||
                    t("pendingResponse")
                  }
                />
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function ToolCallRow({ toolCall }: { toolCall: AgentRuntimeToolCallState }) {
  const [expanded, setExpanded] = useState(false)
  const hasArguments = Boolean(toolCall.arguments)

  return (
    <div
      className="border-b border-border/40 last:border-b-0"
      data-testid="agent-tool-call-row"
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs text-foreground transition-colors hover:bg-muted/40"
        onClick={() => hasArguments && setExpanded((current) => !current)}
        aria-expanded={expanded}
      >
        {hasArguments ? (
          expanded ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          )
        ) : (
          <span className="h-3.5 w-3.5 shrink-0" />
        )}
        <span className="min-w-0 flex-1 truncate font-mono">{toolCall.name}</span>
        <span className="shrink-0 rounded-sm bg-background/70 px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {toolCall.status}
        </span>
      </button>
      {expanded && toolCall.arguments ? (
        <pre className="max-h-56 overflow-auto border-t border-border/40 bg-background/70 px-3 py-2 text-xs leading-5 text-muted-foreground">
          {JSON.stringify(toolCall.arguments, null, 2)}
        </pre>
      ) : null}
    </div>
  )
}

function turnStatusLabel(
  t: (key: string) => string,
  status: AgentRuntimeTurn["status"],
) {
  switch (status) {
    case "queued":
      return t("turnStatus.queued")
    case "running":
      return t("turnStatus.running")
    case "waiting_user":
      return t("turnStatus.waiting_user")
    case "waiting_approval":
      return t("turnStatus.waiting_approval")
    case "completed":
      return t("turnStatus.completed")
    case "failed":
      return t("turnStatus.failed")
    case "cancelled":
      return t("turnStatus.cancelled")
  }
}

function TurnStatusIcon({ status }: { status: AgentRuntimeTurn["status"] }) {
  if (status === "completed") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
  }
  if (status === "failed" || status === "cancelled") {
    return <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
  }
  return <CircleDashed className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
}
