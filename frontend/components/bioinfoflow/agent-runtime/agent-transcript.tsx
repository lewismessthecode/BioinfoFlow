"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Copy,
  RotateCcw,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { ScrollToBottom } from "@/components/bioinfoflow/chat/scroll-to-bottom"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type {
  AgentRuntimeSource,
  AgentRuntimeTimelineEntry,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ActivityGroup } from "./activity-group"
import {
  SourceCitation,
  SourceEvidenceFooter,
  SourcesDrawer,
} from "./agent-sources"
import { InlineApprovalCard } from "./inline-approval-card"
import type { AgentDecisionHandler, AgentRetryHandler } from "./types"

const BOTTOM_FOLLOW_THRESHOLD = 80
const TEXT_SWAP_DURATION_MS = 150

export function AgentTranscript({
  timeline,
  onDecision,
  onRetryTurn,
  eventWindowLimited = false,
}: {
  timeline: AgentRuntimeTimelineEntry[]
  onDecision?: AgentDecisionHandler
  onRetryTurn?: AgentRetryHandler
  eventWindowLimited?: boolean
}) {
  const t = useTranslations("agentRuntime")
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [isFollowingBottom, setIsFollowingBottom] = useState(true)
  const [sourceDrawer, setSourceDrawer] = useState<{
    sources: AgentRuntimeSource[]
    highlightedSourceId: string | null
  } | null>(null)

  const scrollToBottom = useCallback(() => {
    const scroller = scrollRef.current
    if (!scroller) return
    scroller.scrollTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight)
  }, [])

  const updateBottomState = useCallback(() => {
    const scroller = scrollRef.current
    if (!scroller) return
    const distanceFromBottom =
      scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight
    const atBottom = distanceFromBottom <= BOTTOM_FOLLOW_THRESHOLD
    setIsFollowingBottom(atBottom)
  }, [])

  useEffect(() => {
    if (isFollowingBottom) scrollToBottom()
  }, [isFollowingBottom, scrollToBottom, timeline])

  return (
    <div
      ref={scrollRef}
      className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 pt-6 [padding-bottom:var(--agent-composer-bottom-space,8rem)] sm:px-8"
      data-testid="agent-transcript-scroll"
      onScroll={updateBottomState}
    >
      <div className="mx-auto grid w-full min-w-0 max-w-[46rem] gap-10">
        {eventWindowLimited ? (
          <div className="justify-self-start rounded-full border border-border/60 bg-muted/35 px-3 py-1 text-xs text-muted-foreground">
            {t("recentActivityWindow")}
          </div>
        ) : null}
        {timeline.map((entry, index) => {
          const liveStatusLabel = liveTurnStatusLabel(t, entry)
          const responseText = entry.assistant.text.trim()
          const showResponseActions = entry.turn.status === "completed" && responseText.length > 0
          const isLastEntry = index === timeline.length - 1
          return (
            <article
              key={entry.turn.id}
              className={cn(
                "grid min-w-0 gap-3 pb-8",
                !isLastEntry && "border-b border-border/45",
              )}
            >
              <div className="flex justify-end">
                <div className="max-w-[76%] rounded-lg border border-border/60 bg-muted/35 px-3.5 py-2.5 text-[15px] leading-6 text-foreground shadow-none">
                  {entry.turn.input_text}
                </div>
              </div>
              <div className="flex justify-start">
                <div className="w-full min-w-0 max-w-[min(100%,46rem)] px-0">
                  {!liveStatusLabel ? (
                    <TurnStatusLine status={entry.turn.status} />
                  ) : null}

                  {entry.segments.length ? (
                    <div className="grid min-w-0 gap-3">
                      {entry.segments.map((segment) => (
                        <TranscriptSegment
                          key={segment.id}
                          segment={segment}
                          onDecision={onDecision}
                          onOpenSources={(sources, highlightedSourceId = null) =>
                            setSourceDrawer({ sources, highlightedSourceId })
                          }
                        />
                      ))}
                    </div>
                  ) : !isLocalPendingSubmissionTurn(entry.turn) ? (
                    <MarkdownRenderer
                      className="text-[15px] leading-7"
                      content={t("pendingResponse")}
                    />
                  ) : null}
                  {liveStatusLabel ? <LiveStatusLine label={liveStatusLabel} /> : null}
                  {showResponseActions ? (
                    <ResponseActionBar
                      text={responseText}
                      turn={entry.turn}
                      onRetryTurn={onRetryTurn}
                    />
                  ) : null}
                </div>
              </div>
            </article>
          )
        })}
        <div ref={bottomRef} aria-hidden="true" />
      </div>
      <div className="pointer-events-none sticky bottom-5 z-10">
        <div className="pointer-events-auto">
          <ScrollToBottom
            visible={!isFollowingBottom}
            ariaLabel={t("scrollToBottom")}
            onClick={() => {
              setIsFollowingBottom(true)
              scrollToBottom()
            }}
          />
        </div>
      </div>
      <SourcesDrawer
        open={Boolean(sourceDrawer)}
        sources={sourceDrawer?.sources ?? []}
        highlightedSourceId={sourceDrawer?.highlightedSourceId ?? null}
        onOpenChange={(open) => {
          if (!open) setSourceDrawer(null)
        }}
      />
    </div>
  )
}

function TranscriptSegment({
  segment,
  onDecision,
  onOpenSources,
}: {
  segment: AgentRuntimeTranscriptSegment
  onDecision?: AgentDecisionHandler
  onOpenSources?: (sources: AgentRuntimeSource[], highlightedSourceId?: string | null) => void
}) {
  const t = useTranslations("agentRuntime")

  switch (segment.kind) {
    case "assistant_text":
      return <SourceBackedTextSegment segment={segment} onOpenSources={onOpenSources} />
    case "assistant_thinking":
      if (segment.status === "streaming") {
        return null
      }
      return (
        <details className="group text-muted-foreground">
          <summary className="group/summary flex min-h-6 cursor-pointer list-none items-center gap-2 rounded-md px-1 py-0.5 text-xs text-muted-foreground transition-colors hover:bg-muted/25 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring">
            <Brain className="h-3.5 w-3.5 text-muted-foreground/75" />
            <span>{t("thinking")}</span>
            <ChevronDown className="ml-auto h-3.5 w-3.5 text-muted-foreground/70 opacity-0 transition-[opacity,transform] group-open:rotate-180 group-hover/summary:opacity-100 group-focus-visible/summary:opacity-100" />
          </summary>
          <p className="ml-5 mt-1 whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground/80">
            {segment.thinkingBlock.content}
          </p>
        </details>
      )
    case "activity_group":
      return <ActivityGroup group={segment.activityGroup} />
    case "decision":
      return <InlineApprovalCard decision={segment.decision} onDecision={onDecision} />
    case "turn_error":
      return (
        <div className="flex items-start gap-2 rounded-lg border border-border/55 bg-muted/[0.18] px-3 py-2 text-sm leading-6 text-muted-foreground">
          <AlertTriangle className="mt-1 h-4 w-4 shrink-0 text-muted-foreground/75" />
          <span className="break-words">
            {segment.message || t(`turnStatus.${segment.status as AgentRuntimeTurn["status"]}`)}
          </span>
        </div>
      )
  }
}

function SourceBackedTextSegment({
  segment,
  onOpenSources,
}: {
  segment: Extract<AgentRuntimeTranscriptSegment, { kind: "assistant_text" }>
  onOpenSources?: (sources: AgentRuntimeSource[], highlightedSourceId?: string | null) => void
}) {
  const sources = segment.textBlock.sources
  const footerSources = segment.textBlock.footerSources
  const sourceById = new Map(
    sources.flatMap((source) =>
      [source.id, source.citationId, ...(source.citationAliases ?? [])]
        .filter((key): key is string => Boolean(key))
        .map((key) => [key, source] as const),
    ),
  )

  return (
    <div>
      <MarkdownRenderer
        className="text-[15px] leading-7"
        content={segment.textBlock.text}
        allowOverflow={sources.length > 0}
        renderSourceCitation={(sourceId, children) => {
          const source = sourceById.get(sourceId)
          if (!source) return children
          const index = Math.max(0, sources.findIndex((item) => item.id === source.id))
          const citationIndex = numericCitationIndex(sourceId) ?? index
          return (
            <SourceCitation
              source={source}
              index={citationIndex}
              onOpen={(highlightedSourceId) =>
                onOpenSources?.(sources, highlightedSourceId)
              }
            >
              {children}
            </SourceCitation>
          )
        }}
      />
      <SourceEvidenceFooter
        sources={footerSources}
        onOpen={() => onOpenSources?.(footerSources)}
      />
    </div>
  )
}

function TurnStatusLine({ status }: { status: AgentRuntimeTurn["status"] }) {
  const t = useTranslations("agentRuntime")
  return (
    <div className="mb-2.5 flex items-center gap-2 text-xs text-muted-foreground">
      <TurnStatusIcon status={status} />
      <span>{turnStatusLabel(t, status)}</span>
    </div>
  )
}

function LiveStatusLine({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="mt-2 flex min-h-7 items-center gap-2 text-sm text-muted-foreground"
    >
      <CircleDashed className="h-3.5 w-3.5 animate-spin text-muted-foreground/70" />
      <TextSwap text={label} />
    </div>
  )
}

function TextSwap({ text }: { text: string }) {
  const [displayText, setDisplayText] = useState(text)
  const [phase, setPhase] = useState<"idle" | "exit" | "enter-start">("idle")

  useEffect(() => {
    if (text === displayText) return
    let timeout: number | undefined
    let enterFrame: number | undefined
    const frame = window.requestAnimationFrame(() => {
      setPhase("exit")
      timeout = window.setTimeout(() => {
        setDisplayText(text)
        setPhase("enter-start")
        enterFrame = window.requestAnimationFrame(() => setPhase("idle"))
      }, TEXT_SWAP_DURATION_MS)
    })
    return () => {
      window.cancelAnimationFrame(frame)
      if (enterFrame !== undefined) window.cancelAnimationFrame(enterFrame)
      if (timeout !== undefined) window.clearTimeout(timeout)
    }
  }, [displayText, text])

  return (
    <span
      className={
        phase === "exit"
          ? "t-text-swap is-exit"
          : phase === "enter-start"
            ? "t-text-swap is-enter-start"
            : "t-text-swap"
      }
    >
      {displayText}
    </span>
  )
}

function ResponseActionBar({
  text,
  turn,
  onRetryTurn,
}: {
  text: string
  turn: AgentRuntimeTurn
  onRetryTurn?: AgentRetryHandler
}) {
  const t = useTranslations("agentRuntime")
  const copyLabel = t("responseActions.copy")
  const retryLabel = t("responseActions.retry")

  const copyResponse = useCallback(() => {
    void navigator.clipboard?.writeText(text)
  }, [text])

  return (
    <div
      className="mt-3 flex items-center gap-1 text-muted-foreground"
      data-testid="assistant-response-actions"
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={copyLabel}
            title={copyLabel}
            onClick={copyResponse}
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">{copyLabel}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40"
            aria-label={retryLabel}
            title={retryLabel}
            disabled={!onRetryTurn}
            onClick={() => onRetryTurn?.(turn)}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">{retryLabel}</TooltipContent>
      </Tooltip>
    </div>
  )
}

function liveTurnStatusLabel(
  t: (key: string) => string,
  entry: AgentRuntimeTimelineEntry,
) {
  if (entry.turn.status !== "queued" && entry.turn.status !== "running") {
    return null
  }

  const hasStreamingThinking = entry.segments.some(
    (segment) => segment.kind === "assistant_thinking" && segment.status === "streaming",
  )
  if (hasStreamingThinking) return t("statusLine.thinking")

  const hasActiveActivity = entry.activityGroups.some((group) =>
    ["building", "requested", "waiting", "running"].includes(group.status),
  )
  if (hasActiveActivity) return t("statusLine.running")

  const hasStreamingText = entry.assistant.textBlocks.some(
    (block) => block.status === "streaming",
  )
  if (hasStreamingText) return t("statusLine.running")

  if (entry.turn.status === "queued") return t("turnStatus.queued")
  if (entry.turn.status === "running") {
    return t("statusLine.running")
  }
  return null
}

function numericCitationIndex(sourceId: string) {
  if (!/^\d+$/.test(sourceId)) return null
  return Math.max(0, Number(sourceId) - 1)
}

function isLocalPendingSubmissionTurn(turn: AgentRuntimeTurn) {
  return (
    turn.loop_state?.local_queue === true ||
    turn.loop_state?.local_pending_interrupt === true
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
    return <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground/70" />
  }
  if (status === "failed" || status === "cancelled") {
    return <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground/75" />
  }
  return <CircleDashed className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
}
