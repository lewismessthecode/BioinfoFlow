"use client"

import { Fragment, memo, useMemo } from "react"
import type { ReactNode } from "react"
import { useTranslations } from "next-intl"

import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import { AgentMessageParts } from "@/components/bioinfoflow/agent/message-parts"
import { AgentPlanEntry } from "@/components/bioinfoflow/agent/plan-entry"
import { MessageActions } from "@/components/bioinfoflow/agent/message-actions"
import {
  AgentRunOutcome,
  isTerminalRun,
} from "@/components/bioinfoflow/agent/agent-run-outcome"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type {
  HistoryEntry,
  InteractionResponse,
  InteractionResponseEntry,
  MessagePart,
  MessageEntry,
  RunView,
  ToolProgressView,
  ToolResultPart,
} from "@/lib/agent/contracts"
import type { AgentUiCapabilities } from "@/lib/agent/bootstrap"
import { cn } from "@/lib/utils"
import {
  buildTranscriptView,
  scopeLiveToolsByEntry,
} from "@/lib/agent/view-model"

type AgentHistoryEntriesProps = {
  entries: HistoryEntry[]
  runs?: RunView[]
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  onOpenRun?: (runId: string) => void
  onRetryMessage?: (entry: MessageEntry) => void | Promise<void>
  onEditMessage?: (entry: MessageEntry) => void
  capabilities?: AgentUiCapabilities
}

const EMPTY_LIVE_TOOLS = new Map<string, ToolProgressView>()

export const AgentHistoryEntries = memo(function AgentHistoryEntries({
  entries,
  runs = [],
  liveToolsByCallId = EMPTY_LIVE_TOOLS,
  onOpenRun,
  onRetryMessage,
  onEditMessage,
  capabilities,
}: AgentHistoryEntriesProps) {
  const prepared = useMemo(() => buildTranscriptView(entries), [entries])
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
          const visibleParts = filterPartsForCapabilities(
            prepared.visibleMessagePartsByEntryId.get(entry.id) ??
              entry.payload.parts,
            capabilities,
          )
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
                onRetryMessage={onRetryMessage}
                onEditMessage={onEditMessage}
              />
            </div>
          )
        }

        if (
          entry.type === "interaction_request" &&
          (entry.payload.request.type !== "approval" ||
            capabilities?.approvals !== false)
        ) {
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

function isPartCapabilityEnabled(
  part: MessagePart,
  capabilities?: AgentUiCapabilities,
) {
  if (part.type === "reasoning_summary") return capabilities?.reasoning !== false
  if (part.type === "tool_call" || part.type === "tool_result") {
    return capabilities?.toolActivity !== false
  }
  if (part.type === "artifact_ref") return capabilities?.artifacts !== false
  return true
}

function filterPartsForCapabilities(
  parts: MessagePart[],
  capabilities?: AgentUiCapabilities,
) {
  if (
    capabilities?.reasoning !== false &&
    capabilities?.toolActivity !== false &&
    capabilities?.artifacts !== false
  ) {
    return parts
  }
  return parts.filter((part) => isPartCapabilityEnabled(part, capabilities))
}

const AgentHistoryEntry = memo(function AgentHistoryEntry({
  entry,
  messageParts,
  toolResultsByCallId,
  liveToolsByCallId,
  interactionResponse,
  onOpenRun,
  onRetryMessage,
  onEditMessage,
}: {
  entry: Exclude<HistoryEntry, InteractionResponseEntry>
  messageParts?: MessagePart[]
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  interactionResponse?: InteractionResponse
  onOpenRun?: (runId: string) => void
  onRetryMessage?: (entry: MessageEntry) => void | Promise<void>
  onEditMessage?: (entry: MessageEntry) => void
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
        onRetryMessage={onRetryMessage}
        onEditMessage={onEditMessage}
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
})

function MessageHistoryEntry({
  entry,
  parts,
  toolResultsByCallId,
  liveToolsByCallId,
  onOpenRun,
  onRetryMessage,
  onEditMessage,
}: {
  entry: MessageEntry
  parts: MessagePart[]
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  onOpenRun?: (runId: string) => void
  onRetryMessage?: (entry: MessageEntry) => void | Promise<void>
  onEditMessage?: (entry: MessageEntry) => void
}) {
  const isUser = entry.payload.role === "user"
  const copyText = messageCopyText(entry)

  return (
    <article
      className={cn(
        "group/message min-w-0 [content-visibility:auto] [contain-intrinsic-size:auto_96px]",
        isUser && "ml-auto w-fit max-w-[min(92%,46rem)] sm:max-w-[min(85%,46rem)]",
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
      <MessageActions
        createdAt={entry.created_at}
        align={isUser ? "end" : "start"}
        copyText={copyText}
        onRetry={
          !isUser && onRetryMessage ? () => onRetryMessage(entry) : undefined
        }
        onEdit={isUser && onEditMessage ? () => onEditMessage(entry) : undefined}
      />
    </article>
  )
}

function messageCopyText(entry: MessageEntry) {
  return entry.payload.parts
    .flatMap((part) => (part.type === "text" ? [part.text.trim()] : []))
    .filter(Boolean)
    .join("\n\n")
}
