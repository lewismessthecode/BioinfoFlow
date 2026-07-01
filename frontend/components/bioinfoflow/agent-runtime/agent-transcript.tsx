"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { AlertTriangle, Brain, CheckCircle2, ChevronDown, CircleDashed } from "lucide-react"
import { useTranslations } from "next-intl"

import { ScrollToBottom } from "@/components/bioinfoflow/chat/scroll-to-bottom"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type {
  AgentRuntimeSource,
  AgentRuntimeTimelineEntry,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { ActivityGroup } from "./activity-group"
import {
  SourceCitation,
  SourceEvidenceFooter,
  SourcesDrawer,
} from "./agent-sources"
import { InlineApprovalCard } from "./inline-approval-card"
import type { AgentDecisionHandler } from "./types"

const BOTTOM_FOLLOW_THRESHOLD = 80

export function AgentTranscript({
  timeline,
  onDecision,
  eventWindowLimited = false,
}: {
  timeline: AgentRuntimeTimelineEntry[]
  onDecision?: AgentDecisionHandler
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
      className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 pb-32 pt-6 sm:px-8"
      data-testid="agent-transcript-scroll"
      onScroll={updateBottomState}
    >
      <div className="mx-auto grid w-full min-w-0 max-w-4xl gap-10">
        {eventWindowLimited ? (
          <div className="justify-self-start rounded-full border border-border/60 bg-muted/35 px-3 py-1 text-xs text-muted-foreground">
            {t("recentActivityWindow")}
          </div>
        ) : null}
        {timeline.map((entry) => (
          <article
            key={entry.turn.id}
            className="grid min-w-0 gap-3 border-b border-border/45 pb-8 last:border-b-0"
          >
            <div className="flex justify-end">
              <div className="max-w-[76%] rounded-lg border border-border/60 bg-muted/35 px-3.5 py-2.5 text-[15px] leading-6 text-foreground shadow-none">
                {entry.turn.input_text}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="w-full min-w-0 max-w-[min(100%,46rem)] px-0">
                <div className="mb-2.5 flex items-center gap-2 text-xs text-muted-foreground">
                  <TurnStatusIcon status={entry.turn.status} />
                  <span>{turnStatusLabel(t, entry.turn.status)}</span>
                </div>

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
                ) : (
                  <MarkdownRenderer
                    className="text-[15px] leading-7"
                    content={t("pendingResponse")}
                  />
                )}
              </div>
            </div>
          </article>
        ))}
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
        return (
          <div
            className="flex min-h-7 items-center gap-2 text-sm text-muted-foreground"
            role="status"
            aria-live="polite"
          >
            <CircleDashed className="h-3.5 w-3.5 text-muted-foreground/70 motion-safe:animate-spin" />
            <span>{t("statusLine.thinking")}</span>
          </div>
        )
      }
      return (
        <details
          className="group rounded-lg border border-border/60 bg-background px-3 py-2 shadow-none"
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm text-muted-foreground">
            <Brain className="h-4 w-4 text-muted-foreground/75" />
            <span>{t("thinking")}</span>
            <ChevronDown className="ml-auto h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
          </summary>
          <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
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

function numericCitationIndex(sourceId: string) {
  if (!/^\d+$/.test(sourceId)) return null
  return Math.max(0, Number(sourceId) - 1)
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
