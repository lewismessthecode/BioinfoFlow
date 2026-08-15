"use client"

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import { useTranslations } from "next-intl"

import { ActiveRun } from "@/components/bioinfoflow/agent/active-run"
import { AgentHistoryEntries } from "@/components/bioinfoflow/agent/conversation-entries"
import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import { Button } from "@/components/ui/button"
import { ArrowDown } from "@/lib/icons"
import { collectDurableToolCallIds } from "@/lib/agent/activity"
import type {
  ActiveRunView,
  HistoryEntry,
  InteractionResponse,
  RunView,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type AgentTranscriptProps = {
  entries: HistoryEntry[]
  runs: RunView[]
  activeRun: ActiveRunView | null
  onRespond?: (
    interactionId: string,
    response: InteractionResponse,
  ) => void | Promise<void>
  onOpenRun?: (runId: string) => void
  className?: string
}

const BOTTOM_THRESHOLD_PX = 96
const READ_ANCHOR_ATTRIBUTE = "data-agent-read-anchor"

type TranscriptReadAnchor = {
  id: string
  offset: number
}

export function AgentTranscript({
  entries,
  runs,
  activeRun,
  onRespond,
  onOpenRun,
  className,
}: AgentTranscriptProps) {
  const t = useTranslations("agentTranscript")
  const contentRevision = transcriptContentRevision(entries, runs, activeRun)
  const scrollRef = useRef<HTMLElement>(null)
  const initializedRef = useRef(false)
  const contentRevisionRef = useRef(contentRevision)
  const readAnchorRef = useRef<TranscriptReadAnchor | null>(null)
  const [followingBottom, setFollowingBottom] = useState(true)
  const [hasNewContent, setHasNewContent] = useState(false)
  const pendingInteraction = activeRun?.pending_interaction ?? null
  const pendingInteractionId = pendingInteraction?.interaction_id ?? null
  const durableEntries = useMemo(
    () =>
      pendingInteractionId
        ? entries.filter(
            (entry) =>
              entry.type !== "interaction_request" ||
              entry.payload.interaction_id !== pendingInteractionId,
          )
        : entries,
    [entries, pendingInteractionId],
  )
  const durableToolCallIds = useMemo(
    () => collectDurableToolCallIds(durableEntries),
    [durableEntries],
  )
  const liveToolsByCallId = useMemo(
    () =>
      new Map(
        (activeRun?.tool_progress ?? []).map((tool) => [tool.call_id, tool]),
      ),
    [activeRun?.tool_progress],
  )
  useLayoutEffect(() => {
    const scrollElement = scrollRef.current
    if (!scrollElement || followingBottom) return
    const anchor = readAnchorRef.current
    if (!anchor) {
      readAnchorRef.current = captureReadAnchor(scrollElement)
      return
    }
    const anchorElement = findReadAnchor(scrollElement, anchor.id)
    if (!anchorElement) {
      readAnchorRef.current = captureReadAnchor(scrollElement)
      return
    }
    const currentOffset =
      anchorElement.getBoundingClientRect().top -
      scrollElement.getBoundingClientRect().top
    scrollElement.scrollTop += currentOffset - anchor.offset
  }, [activeRun, entries, followingBottom, runs])

  useEffect(() => {
    const scrollElement = scrollRef.current
    if (!scrollElement) return
    const contentChanged = contentRevisionRef.current !== contentRevision
    contentRevisionRef.current = contentRevision

    if (followingBottom && (!initializedRef.current || contentChanged)) {
      scrollToBottom(scrollElement, "follow")
    } else if (!followingBottom && initializedRef.current && contentChanged) {
      const frame = window.requestAnimationFrame(() => setHasNewContent(true))
      return () => window.cancelAnimationFrame(frame)
    }
    initializedRef.current = true
  }, [contentRevision, followingBottom])

  function handleScroll() {
    const scrollElement = scrollRef.current
    if (!scrollElement) return
    const nearBottom = isNearBottom(scrollElement)
    setFollowingBottom(nearBottom)
    if (nearBottom) {
      readAnchorRef.current = null
      setHasNewContent(false)
      return
    }
    readAnchorRef.current = captureReadAnchor(scrollElement)
  }

  function jumpToLatest() {
    const scrollElement = scrollRef.current
    if (!scrollElement) return
    setFollowingBottom(true)
    readAnchorRef.current = null
    setHasNewContent(false)
    scrollToBottom(scrollElement, "jump")
  }

  return (
    <div className={cn("relative min-h-0 min-w-0", className)}>
      <section
        ref={scrollRef}
        aria-label={t("title")}
        className="grid h-full min-h-0 min-w-0 content-start gap-5 overflow-x-clip overflow-y-auto px-3 py-4 sm:px-5"
        data-testid="agent-transcript"
        onScroll={handleScroll}
      >
        <AgentHistoryEntries
          entries={durableEntries}
          runs={runs}
          liveToolsByCallId={liveToolsByCallId}
          onOpenRun={onOpenRun}
        />
        {activeRun ? (
          <ActiveRun
            activeRun={activeRun}
            durableToolCallIds={durableToolCallIds}
          />
        ) : null}
        {pendingInteraction ? (
          <AgentInteractionCard
            interactionId={pendingInteraction.interaction_id}
            request={pendingInteraction.request}
            onRespond={
              onRespond
                ? (response) =>
                    onRespond(pendingInteraction.interaction_id, response)
                : undefined
            }
          />
        ) : null}
      </section>

      {hasNewContent ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center px-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="pointer-events-auto border-border/70 bg-background text-muted-foreground shadow-sm hover:text-foreground motion-reduce:transition-none"
            aria-label={t("scroll_to_bottom")}
            onClick={jumpToLatest}
          >
            <ArrowDown data-icon="inline-start" aria-hidden="true" />
            {t("scroll_to_bottom")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function transcriptContentRevision(
  entries: HistoryEntry[],
  runs: RunView[],
  activeRun: ActiveRunView | null,
) {
  const lastEntry = entries.at(-1)
  const draftRevision = activeRun?.assistant_draft?.parts
    .map((part) => `${part.id}:${part.end_offset}`)
    .join("|")
  const toolRevision = activeRun?.tool_progress
    .map((tool) => `${tool.call_id}:${tool.revision}`)
    .join("|")
  const runRevision = runs
    .map((run) => `${run.id}:${run.revision}:${run.status}`)
    .join("|")

  return [
    entries.length,
    lastEntry?.id,
    lastEntry?.sequence,
    runRevision,
    activeRun?.run.revision,
    draftRevision,
    toolRevision,
    activeRun?.pending_interaction?.revision,
  ].join(":")
}

function isNearBottom(element: HTMLElement) {
  return (
    element.scrollHeight - element.scrollTop - element.clientHeight <=
    BOTTOM_THRESHOLD_PX
  )
}

function captureReadAnchor(element: HTMLElement): TranscriptReadAnchor | null {
  const containerRect = element.getBoundingClientRect()
  for (const candidate of element.querySelectorAll<HTMLElement>(
    `[${READ_ANCHOR_ATTRIBUTE}]`,
  )) {
    const rect = candidate.getBoundingClientRect()
    if (rect.bottom <= containerRect.top || rect.top >= containerRect.bottom) {
      continue
    }
    const id = candidate.getAttribute(READ_ANCHOR_ATTRIBUTE)
    if (id) return { id, offset: rect.top - containerRect.top }
  }
  return null
}

function findReadAnchor(element: HTMLElement, id: string) {
  return Array.from(
    element.querySelectorAll<HTMLElement>(`[${READ_ANCHOR_ATTRIBUTE}]`),
  ).find((candidate) => candidate.getAttribute(READ_ANCHOR_ATTRIBUTE) === id)
}

function scrollToBottom(element: HTMLElement, mode: "follow" | "jump") {
  const behavior =
    mode === "follow" || prefersReducedMotion() ? "auto" : "smooth"
  if (typeof element.scrollTo === "function") {
    element.scrollTo({ top: element.scrollHeight, behavior })
    return
  }
  element.scrollTop = element.scrollHeight
}

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
}
