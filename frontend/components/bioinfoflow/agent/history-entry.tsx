"use client"

import { useMemo } from "react"
import { useTranslations } from "next-intl"

import { AgentMessageParts } from "@/components/bioinfoflow/agent/message-parts"
import { AgentPlanEntry } from "@/components/bioinfoflow/agent/plan-entry"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  HistoryEntry,
  InteractionRequest,
  InteractionRequestEntry,
  InteractionResponse,
  InteractionResponseEntry,
  MessageEntry,
  PlanEntry,
  ToolResultPart,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type AgentHistoryEntriesProps = {
  entries: HistoryEntry[]
}

export function AgentHistoryEntries({ entries }: AgentHistoryEntriesProps) {
  const prepared = useMemo(() => prepareHistory(entries), [entries])

  return (
    <div className="grid min-w-0 gap-5" data-testid="agent-history-entries">
      {prepared.entries.map((entry) => {
        if (
          entry.type === "plan" &&
          prepared.latestPlanEntryIds.get(entry.payload.plan_id) !== entry.id
        ) {
          return null
        }

        if (entry.type === "interaction_response") return null

        if (entry.type === "message") {
          const visibleParts =
            entry.payload.role === "tool"
              ? entry.payload.parts.filter(
                  (part) =>
                    part.type !== "tool_result" ||
                    !prepared.consumedToolCallIds.has(part.call_id),
                )
              : entry.payload.parts
          if (visibleParts.length === 0) return null

          return (
            <AgentHistoryEntry
              key={entry.id}
              entry={{
                ...entry,
                payload: { ...entry.payload, parts: visibleParts },
              }}
              toolResultsByCallId={prepared.toolResultsByCallId}
            />
          )
        }

        if (entry.type === "interaction_request") {
          return (
            <AgentHistoryEntry
              key={entry.id}
              entry={entry}
              interactionResponse={prepared.interactionResponses.get(
                entry.payload.interaction_id,
              )}
            />
          )
        }

        return <AgentHistoryEntry key={entry.id} entry={entry} />
      })}
    </div>
  )
}

export function AgentHistoryEntry({
  entry,
  toolResultsByCallId,
  interactionResponse,
}: {
  entry: Exclude<HistoryEntry, InteractionResponseEntry>
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  interactionResponse?: InteractionResponse
}) {
  const t = useTranslations("agentHistory")

  if (entry.type === "message") {
    return (
      <MessageHistoryEntry
        entry={entry}
        toolResultsByCallId={toolResultsByCallId}
      />
    )
  }

  if (entry.type === "plan") {
    return <AgentPlanEntry entry={entry} />
  }

  if (entry.type === "interaction_request") {
    return (
      <HistoricalInteraction
        entry={entry}
        response={interactionResponse}
      />
    )
  }

  if (entry.type === "notice") {
    return (
      <Alert
        role="note"
        className="border-border/60 bg-muted/20 [content-visibility:auto] [contain-intrinsic-size:auto_96px]"
      >
        <AlertTitle>{t("notice.title")}</AlertTitle>
        <AlertDescription>{entry.payload.message}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground [content-visibility:auto] [contain-intrinsic-size:auto_48px]">
      <span className="h-px flex-1 bg-border/60" aria-hidden="true" />
      <span>{t("compaction")}</span>
      <span className="h-px flex-1 bg-border/60" aria-hidden="true" />
    </div>
  )
}

function MessageHistoryEntry({
  entry,
  toolResultsByCallId,
}: {
  entry: MessageEntry
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
}) {
  const isUser = entry.payload.role === "user"

  return (
    <article
      className={cn(
        "min-w-0 [content-visibility:auto] [contain-intrinsic-size:auto_96px]",
        isUser && "ml-auto w-fit max-w-[min(85%,46rem)]",
      )}
      data-role={entry.payload.role}
    >
      <div
        className={cn(
          "min-w-0",
          isUser &&
            "rounded-[12px] border border-border/60 bg-muted/35 px-3.5 py-3",
        )}
      >
        <AgentMessageParts
          parts={entry.payload.parts}
          toolResultsByCallId={toolResultsByCallId}
        />
      </div>
    </article>
  )
}

function HistoricalInteraction({
  entry,
  response,
}: {
  entry: InteractionRequestEntry
  response?: InteractionResponse
}) {
  const t = useTranslations("agentHistory")
  const view = interactionView(entry.payload.request)
  const status = interactionStatus(entry.payload.request, response)
  const tone = interactionTone(status)

  return (
    <section
      className={cn(
        "grid gap-3 rounded-[10px] border px-3.5 py-3 [content-visibility:auto] [contain-intrinsic-size:auto_128px]",
        tone === "warning" && "border-warning-border bg-warning-muted/25",
        tone === "success" && "border-success-border bg-success-muted/25",
        tone === "destructive" && "border-error-border bg-error-muted/25",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">
          {t(`interaction.${view.kind}`)}
        </h2>
        <StatusBadge variant={tone}>{t(`interaction.${status}`)}</StatusBadge>
      </div>
      <p className="text-sm leading-6 text-foreground/80">{view.summary}</p>
      {view.preview ? (
        <pre
          className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-background/70 px-3 py-2 font-mono text-xs leading-5 text-foreground/70"
          translate="no"
        >
          {view.preview}
        </pre>
      ) : null}
      {view.details.length > 0 ? (
        <ul className="grid gap-1 text-xs leading-5 text-muted-foreground">
          {view.details.map((detail, index) => (
            <li key={`${index}:${detail}`}>{detail}</li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function prepareHistory(entries: HistoryEntry[]) {
  const toolResultsByCallId = new Map<string, ToolResultPart>()
  const consumedToolCallIds = new Set<string>()
  const interactionResponses = new Map<string, InteractionResponse>()
  const latestPlans = new Map<string, PlanEntry>()
  const sortedEntries = [...entries].sort((left, right) =>
    left.sequence === right.sequence
      ? left.created_at.localeCompare(right.created_at)
      : left.sequence - right.sequence,
  )

  for (const entry of sortedEntries) {
    if (entry.type === "message") {
      for (const part of entry.payload.parts) {
        if (part.type === "tool_result") {
          toolResultsByCallId.set(part.call_id, part)
        }
        if (part.type === "tool_call") {
          consumedToolCallIds.add(part.call_id)
        }
      }
    }

    if (entry.type === "interaction_response") {
      interactionResponses.set(
        entry.payload.interaction_id,
        entry.payload.response,
      )
    }

    if (entry.type === "plan") {
      const latest = latestPlans.get(entry.payload.plan_id)
      if (
        !latest ||
        entry.payload.revision > latest.payload.revision ||
        (entry.payload.revision === latest.payload.revision &&
          entry.sequence > latest.sequence)
      ) {
        latestPlans.set(entry.payload.plan_id, entry)
      }
    }
  }

  return {
    entries: sortedEntries,
    toolResultsByCallId,
    consumedToolCallIds,
    interactionResponses,
    latestPlanEntryIds: new Map(
      [...latestPlans].map(([planId, entry]) => [planId, entry.id]),
    ),
  }
}

function interactionView(request: InteractionRequest) {
  if (request.type === "approval") {
    return {
      kind: "approval" as const,
      summary: request.summary,
      preview: request.input_preview,
      details: request.risk.effects,
    }
  }
  if (request.type === "ask_user") {
    return {
      kind: "ask_user" as const,
      summary: request.questions.map((question) => question.question).join(" "),
      preview: null,
      details: request.questions.flatMap((question) =>
        question.options.map((option) => option.label),
      ),
    }
  }
  return {
    kind: "recovery" as const,
    summary: request.message,
    preview: null,
    details: request.options.map((option) => option.label),
  }
}

function interactionStatus(
  request: InteractionRequest,
  response?: InteractionResponse,
) {
  if (!response || response.type !== request.type) return "pending" as const
  if (response.type === "approval") {
    return response.approved ? ("approved" as const) : ("rejected" as const)
  }
  if (response.type === "ask_user") return "answered" as const
  return "resolved" as const
}

function interactionTone(status: ReturnType<typeof interactionStatus>) {
  if (status === "pending") return "warning" as const
  if (status === "rejected") return "destructive" as const
  return "success" as const
}
