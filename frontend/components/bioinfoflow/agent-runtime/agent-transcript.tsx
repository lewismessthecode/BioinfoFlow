"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { AlertTriangle, CheckCircle2, ChevronDown, CircleDashed } from "lucide-react"
import { useTranslations } from "next-intl"

import { ScrollToBottom } from "@/components/bioinfoflow/chat/scroll-to-bottom"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type {
  AgentRuntimeTimelineEntry,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { ActivityGroup } from "./activity-group"
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
      className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 pb-36 pt-8 sm:px-6"
      data-testid="agent-transcript-scroll"
      onScroll={updateBottomState}
    >
      <div className="mx-auto grid w-full min-w-0 max-w-3xl gap-8">
        {eventWindowLimited ? (
          <div className="justify-self-start rounded-full border border-border/60 bg-muted/35 px-3 py-1 text-xs text-muted-foreground">
            {t("recentActivityWindow")}
          </div>
        ) : null}
        {timeline.map((entry) => (
          <article key={entry.turn.id} className="grid min-w-0 gap-4">
            <div className="flex justify-end">
              <div className="max-w-[82%] rounded-[22px] bg-muted px-4 py-3 text-[15px] leading-6 text-foreground">
                {entry.turn.input_text}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="w-full min-w-0 max-w-[88%] px-1">
                <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
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
    </div>
  )
}

function TranscriptSegment({
  segment,
  onDecision,
}: {
  segment: AgentRuntimeTranscriptSegment
  onDecision?: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")

  switch (segment.kind) {
    case "assistant_text":
      return (
        <MarkdownRenderer
          className="text-[15px] leading-7"
          content={segment.textBlock.text}
        />
      )
    case "assistant_thinking":
      return (
        <details
          className="group rounded-2xl border border-border/50 bg-muted/20 px-3 py-2"
          open
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-foreground">
            <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
            <span>{t("thinking")}</span>
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
        <div className="flex items-start gap-2 rounded-2xl border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm leading-6 text-destructive">
          <AlertTriangle className="mt-1 h-4 w-4 shrink-0" />
          <span className="break-words">
            {segment.message || t(`turnStatus.${segment.status as AgentRuntimeTurn["status"]}`)}
          </span>
        </div>
      )
  }
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
