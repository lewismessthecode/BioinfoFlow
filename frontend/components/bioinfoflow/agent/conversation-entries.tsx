"use client"

import { Fragment, memo, useMemo, useState } from "react"
import type { ReactNode } from "react"
import { useLocale, useTranslations } from "next-intl"

import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import { AgentMessageParts } from "@/components/bioinfoflow/agent/message-parts"
import { AgentPlanEntry } from "@/components/bioinfoflow/agent/plan-entry"
import {
  AgentRunOutcome,
  isTerminalRun,
} from "@/components/bioinfoflow/agent/agent-run-outcome"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Check, Copy } from "@/lib/icons"
import {
  dateTimeAttribute,
  formatAbsoluteDateTime,
  formatAgentEndTime,
} from "@/lib/agent/date-format"
import type {
  HistoryEntry,
  InteractionResponse,
  InteractionResponseEntry,
  MessagePart,
  MessageEntry,
  PlanEntry,
  RunView,
  ToolProgressView,
  ToolResultPart,
} from "@/lib/agent/contracts"
import {
  interactionFromLegacy,
  planFromLegacy,
} from "@/lib/agent/projection/legacy-transcript-adapter"
import { cn } from "@/lib/utils"

type AgentHistoryEntriesProps = {
  entries: HistoryEntry[]
  runs?: RunView[]
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  onOpenRun?: (runId: string) => void
}

const EMPTY_LIVE_TOOLS = new Map<string, ToolProgressView>()

export const AgentHistoryEntries = memo(function AgentHistoryEntries({
  entries,
  runs = [],
  liveToolsByCallId = EMPTY_LIVE_TOOLS,
  onOpenRun,
}: AgentHistoryEntriesProps) {
  const prepared = useMemo(() => prepareHistory(entries), [entries])
  const runsById = useMemo(
    () => new Map(runs.map((run) => [run.id, run])),
    [runs],
  )
  const orphanedOutcomes = useMemo(
    () =>
      runs
        .filter(isTerminalRun)
        .filter((run) => !prepared.lastEntryIdsByRun.has(run.id)),
    [prepared.lastEntryIdsByRun, runs],
  )
  const liveToolsByEntryId = useMemo(
    () =>
      scopeLiveToolsByEntry(
        liveToolsByCallId,
        prepared.toolCallEntryIdsByCallId,
      ),
    [liveToolsByCallId, prepared.toolCallEntryIdsByCallId],
  )

  return (
    <div className="grid min-w-0 gap-5" data-testid="agent-history-entries">
      {prepared.entries.map((entry) => {
        const run = entry.run_id ? runsById.get(entry.run_id) : undefined
        const outcome =
          run &&
          isTerminalRun(run) &&
          prepared.lastEntryIdsByRun.get(run.id) === entry.id
            ? run
            : null
        const withOutcome = (content: ReactNode) => (
          <Fragment key={entry.id}>
            {content}
            {outcome ? <AgentRunOutcome run={outcome} /> : null}
          </Fragment>
        )

        if (
          entry.type === "plan" &&
          prepared.latestPlanEntryIds.get(entry.payload.plan_id) !== entry.id
        ) {
          return withOutcome(null)
        }

        if (entry.type === "interaction_response") return withOutcome(null)

        if (entry.type === "message") {
          const visibleParts =
            prepared.visibleMessagePartsByEntryId.get(entry.id) ??
            entry.payload.parts
          if (visibleParts.length === 0) return withOutcome(null)

          return withOutcome(
            <div
              className="min-w-0"
              data-agent-read-anchor={`entry:${entry.id}`}
            >
              <AgentHistoryEntry
                entry={entry}
                messageParts={visibleParts}
                toolResultsByCallId={prepared.toolResultsByCallId}
                liveToolsByCallId={
                  liveToolsByEntryId.get(entry.id) ?? EMPTY_LIVE_TOOLS
                }
                onOpenRun={onOpenRun}
              />
            </div>
          )
        }

        if (entry.type === "interaction_request") {
          return withOutcome(
            <div
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

        return withOutcome(
          <div
            className="min-w-0"
            data-agent-read-anchor={`entry:${entry.id}`}
          >
            <AgentHistoryEntry entry={entry} />
          </div>
        )
      })}
      {orphanedOutcomes.map((run) => (
        <AgentRunOutcome key={run.id} run={run} />
      ))}
    </div>
  )
})

const AgentHistoryEntry = memo(function AgentHistoryEntry({
  entry,
  messageParts,
  toolResultsByCallId,
  liveToolsByCallId,
  interactionResponse,
  onOpenRun,
}: {
  entry: Exclude<HistoryEntry, InteractionResponseEntry>
  messageParts?: MessagePart[]
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  interactionResponse?: InteractionResponse
  onOpenRun?: (runId: string) => void
}) {
  const t = useTranslations("agentHistory")

  if (entry.type === "message") {
    return (
      <MessageHistoryEntry
        entry={entry}
        parts={messageParts ?? entry.payload.parts}
        toolResultsByCallId={toolResultsByCallId}
        liveToolsByCallId={liveToolsByCallId}
        onOpenRun={onOpenRun}
      />
    )
  }

  if (entry.type === "plan") {
    return <AgentPlanEntry plan={planFromLegacy(entry)} />
  }

  if (entry.type === "interaction_request") {
    return (
      <AgentInteractionCard
        interaction={interactionFromLegacy(
          entry.payload.interaction_id,
          entry.payload.request,
          interactionResponse ?? null,
        )}
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
})

function MessageHistoryEntry({
  entry,
  parts,
  toolResultsByCallId,
  liveToolsByCallId,
  onOpenRun,
}: {
  entry: MessageEntry
  parts: MessagePart[]
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  onOpenRun?: (runId: string) => void
}) {
  const isUser = entry.payload.role === "user"
  const t = useTranslations("agentTranscript")
  const locale = useLocale()
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  )
  const copyText = messageCopyText(entry)
  const isConversationalMessage =
    entry.payload.role === "user" || entry.payload.role === "assistant"
  const canCopy =
    isConversationalMessage && copyText.length > 0
  const timestamp = isConversationalMessage
    ? formatAgentEndTime(entry.created_at, locale)
    : null
  const absoluteTimestamp = isConversationalMessage
    ? formatAbsoluteDateTime(entry.created_at, locale)
    : null

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
        isUser && "ml-auto w-fit max-w-[76%]",
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
          parts={parts}
          toolResultsByCallId={toolResultsByCallId}
          liveToolsByCallId={liveToolsByCallId}
          onOpenRun={onOpenRun}
        />
      </div>
      {canCopy || timestamp ? (
        <footer
          className={cn(
            "mt-1.5 flex min-w-0 items-center gap-1 text-[11px] leading-none text-muted-foreground/65",
            isUser ? "justify-end" : "justify-start",
          )}
        >
          {canCopy ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t(copyState === "copied" ? "copied" : "copy")}
              className="size-7 text-muted-foreground/65 hover:bg-muted/45 hover:text-foreground"
              onClick={() => void copyMessage()}
            >
              {copyState === "copied" ? (
                <Check data-icon="inline-start" aria-hidden="true" />
              ) : (
                <Copy data-icon="inline-start" aria-hidden="true" />
              )}
            </Button>
          ) : null}
          {timestamp ? (
            <time
              dateTime={dateTimeAttribute(entry.created_at)}
              title={absoluteTimestamp ?? timestamp}
              data-testid={
                isUser
                  ? "agent-user-message-timestamp"
                  : "assistant-response-timestamp"
              }
              suppressHydrationWarning
              translate="no"
            >
              {timestamp}
            </time>
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
  const lastEntryIdsByRun = new Map<string, string>()
  const toolCallEntryIdsByCallId = new Map<string, string>()
  const sortedEntries = [...entries].sort((left, right) =>
    left.sequence === right.sequence
      ? left.created_at.localeCompare(right.created_at)
      : left.sequence - right.sequence,
  )

  for (const entry of sortedEntries) {
    if (entry.run_id) lastEntryIdsByRun.set(entry.run_id, entry.id)
    if (entry.type === "message") {
      for (const part of entry.payload.parts) {
        if (part.type === "tool_result") {
          toolResultsByCallId.set(part.call_id, part)
        }
        if (part.type === "tool_call") {
          consumedToolCallIds.add(part.call_id)
          toolCallEntryIdsByCallId.set(part.call_id, entry.id)
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
    toolCallEntryIdsByCallId,
    visibleMessagePartsByEntryId: new Map(
      sortedEntries.flatMap((entry) => {
        if (entry.type !== "message") return []
        const parts =
          entry.payload.role === "tool"
            ? entry.payload.parts.filter(
                (part) =>
                  part.type !== "tool_result" ||
                  !consumedToolCallIds.has(part.call_id),
              )
            : entry.payload.parts
        return [[entry.id, parts] as const]
      }),
    ),
    interactionResponses,
    lastEntryIdsByRun,
    latestPlanEntryIds: new Map(
      [...latestPlans].map(([planId, entry]) => [planId, entry.id]),
    ),
  }
}

function scopeLiveToolsByEntry(
  liveToolsByCallId: ReadonlyMap<string, ToolProgressView>,
  toolCallEntryIdsByCallId: ReadonlyMap<string, string>,
) {
  const result = new Map<string, Map<string, ToolProgressView>>()
  for (const [callId, tool] of liveToolsByCallId) {
    const entryId = toolCallEntryIdsByCallId.get(callId)
    if (!entryId) continue
    const entryTools = result.get(entryId)
    if (entryTools) {
      entryTools.set(callId, tool)
    } else {
      result.set(entryId, new Map([[callId, tool]]))
    }
  }
  return result
}

function messageCopyText(entry: MessageEntry) {
  return entry.payload.parts
    .flatMap((part) => (part.type === "text" ? [part.text.trim()] : []))
    .filter(Boolean)
    .join("\n\n")
}
