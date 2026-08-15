"use client"

import { memo, useMemo, useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import { AgentMessageParts } from "@/components/bioinfoflow/agent/message-parts"
import { AgentPlanEntry } from "@/components/bioinfoflow/agent/plan-entry"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Check, Copy } from "@/lib/icons"
import {
  dateTimeAttribute,
  formatAgentDuration,
  formatAgentEndTime,
} from "@/lib/agent/date-format"
import type {
  HistoryEntry,
  InteractionResponse,
  InteractionResponseEntry,
  MessageEntry,
  PlanEntry,
  RunView,
  ToolResultPart,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type AgentHistoryEntriesProps = {
  entries: HistoryEntry[]
  runs?: RunView[]
}

export const AgentHistoryEntries = memo(function AgentHistoryEntries({
  entries,
  runs = [],
}: AgentHistoryEntriesProps) {
  const prepared = useMemo(() => prepareHistory(entries), [entries])
  const runsById = useMemo(
    () => new Map(runs.map((run) => [run.id, run])),
    [runs],
  )

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
            <div
              key={entry.id}
              className="min-w-0"
              data-agent-read-anchor={`entry:${entry.id}`}
            >
              <AgentHistoryEntry
                entry={{
                  ...entry,
                  payload: { ...entry.payload, parts: visibleParts },
                }}
                toolResultsByCallId={prepared.toolResultsByCallId}
                run={entry.run_id ? runsById.get(entry.run_id) : undefined}
                showRunCompletion={
                  entry.payload.role === "assistant" &&
                  Boolean(entry.run_id) &&
                  prepared.latestAssistantEntryIdsByRun.get(
                    entry.run_id ?? "",
                  ) === entry.id
                }
              />
            </div>
          )
        }

        if (entry.type === "interaction_request") {
          return (
            <div
              key={entry.id}
              className="min-w-0"
              data-agent-read-anchor={`entry:${entry.id}`}
            >
              <AgentHistoryEntry
                entry={entry}
                interactionResponse={prepared.interactionResponses.get(
                  entry.payload.interaction_id,
                )}
              />
            </div>
          )
        }

        return (
          <div
            key={entry.id}
            className="min-w-0"
            data-agent-read-anchor={`entry:${entry.id}`}
          >
            <AgentHistoryEntry entry={entry} />
          </div>
        )
      })}
    </div>
  )
})

function AgentHistoryEntry({
  entry,
  toolResultsByCallId,
  interactionResponse,
  run,
  showRunCompletion = false,
}: {
  entry: Exclude<HistoryEntry, InteractionResponseEntry>
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  interactionResponse?: InteractionResponse
  run?: RunView
  showRunCompletion?: boolean
}) {
  const t = useTranslations("agentHistory")

  if (entry.type === "message") {
    return (
      <MessageHistoryEntry
        entry={entry}
        toolResultsByCallId={toolResultsByCallId}
        run={run}
        showRunCompletion={showRunCompletion}
      />
    )
  }

  if (entry.type === "plan") {
    return <AgentPlanEntry entry={entry} />
  }

  if (entry.type === "interaction_request") {
    return (
      <AgentInteractionCard
        interactionId={entry.payload.interaction_id}
        request={entry.payload.request}
        response={interactionResponse}
      />
    )
  }

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

function MessageHistoryEntry({
  entry,
  toolResultsByCallId,
  run,
  showRunCompletion,
}: {
  entry: MessageEntry
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  run?: RunView
  showRunCompletion: boolean
}) {
  const isUser = entry.payload.role === "user"
  const t = useTranslations("agentTranscript")
  const locale = useLocale()
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  )
  const copyText = messageCopyText(entry)
  const canCopy =
    (entry.payload.role === "user" || entry.payload.role === "assistant") &&
    copyText.length > 0
  const runCompletion =
    showRunCompletion && run ? completedRunView(run, locale) : null

  async function copyMessage() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(copyText)
      setCopyState("copied")
    } catch {
      setCopyState("failed")
    }
  }

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
      {canCopy || runCompletion ? (
        <footer
          className={cn(
            "mt-1.5 flex min-w-0 items-center gap-2 text-[11px] text-muted-foreground",
            isUser ? "justify-end" : "justify-start",
          )}
        >
          {runCompletion ? (
            <div className="flex min-w-0 flex-wrap items-center gap-1.5 tabular-nums">
              <time dateTime={runCompletion.dateTime} translate="no">
                {t("run_finished", { time: runCompletion.time })}
              </time>
              <span aria-hidden="true">·</span>
              <span translate="no">
                {t("run_duration", { duration: runCompletion.duration })}
              </span>
            </div>
          ) : null}
          {canCopy ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t(copyState === "copied" ? "copied" : "copy")}
              className="text-muted-foreground hover:text-foreground"
              onClick={() => void copyMessage()}
            >
              {copyState === "copied" ? (
                <Check data-icon="inline-start" aria-hidden="true" />
              ) : (
                <Copy data-icon="inline-start" aria-hidden="true" />
              )}
            </Button>
          ) : null}
        </footer>
      ) : null}
      {copyState === "failed" ? (
        <p
          role="alert"
          aria-live="polite"
          className={cn(
            "mt-1 text-xs leading-5 text-error-foreground",
            isUser && "text-right",
          )}
        >
          {t("copy_failed")}
        </p>
      ) : null}
    </article>
  )
}

function prepareHistory(entries: HistoryEntry[]) {
  const toolResultsByCallId = new Map<string, ToolResultPart>()
  const consumedToolCallIds = new Set<string>()
  const interactionResponses = new Map<string, InteractionResponse>()
  const latestPlans = new Map<string, PlanEntry>()
  const latestAssistantEntryIdsByRun = new Map<string, string>()
  const sortedEntries = [...entries].sort((left, right) =>
    left.sequence === right.sequence
      ? left.created_at.localeCompare(right.created_at)
      : left.sequence - right.sequence,
  )

  for (const entry of sortedEntries) {
    if (entry.type === "message") {
      if (entry.payload.role === "assistant" && entry.run_id) {
        latestAssistantEntryIdsByRun.set(entry.run_id, entry.id)
      }
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
    latestAssistantEntryIdsByRun,
    latestPlanEntryIds: new Map(
      [...latestPlans].map(([planId, entry]) => [planId, entry.id]),
    ),
  }
}

function messageCopyText(entry: MessageEntry) {
  return entry.payload.parts
    .flatMap((part) => (part.type === "text" ? [part.text.trim()] : []))
    .filter(Boolean)
    .join("\n\n")
}

function completedRunView(run: RunView, locale: string) {
  const time = formatAgentEndTime(run.completed_at, locale)
  const duration = formatAgentDuration(
    run.started_at,
    run.completed_at,
    locale,
  )
  if (!time || !duration) return null

  return {
    time,
    duration,
    dateTime: dateTimeAttribute(run.completed_at),
  }
}
