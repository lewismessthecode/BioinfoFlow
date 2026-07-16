"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Copy,
  Download,
  FileText,
  RotateCcw,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { ScrollToBottom } from "@/components/bioinfoflow/chat/scroll-to-bottom"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { buildAgentFsDownloadUrl, deliverableArtifacts } from "@/lib/agent-runtime"
import type {
  AgentRuntimeSource,
  AgentRuntimeArtifact,
  AgentRuntimeTimelineEntry,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import {
  SourceCitation,
  SourceEvidenceFooter,
  SourcesDrawer,
} from "./agent-sources"
import {
  artifactDisplaySubtitle,
  artifactDisplayTitle,
  artifactFilePath,
} from "./artifact-display"
import { artifactTypeLabel } from "./artifact-viewers"
import { InlineApprovalCard } from "./inline-approval-card"
import type { AgentDecisionHandler, AgentRetryHandler } from "./types"

const BOTTOM_FOLLOW_THRESHOLD = 80
const TEXT_SWAP_DURATION_MS = 150

export function AgentTranscript({
  timeline,
  artifacts = [],
  onOpenArtifact,
  onDecision,
  onRetryTurn,
  eventWindowLimited = false,
}: {
  timeline: AgentRuntimeTimelineEntry[]
  artifacts?: AgentRuntimeArtifact[]
  onOpenArtifact?: (artifactId: string) => void
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
  const visibleArtifacts = useMemo(() => deliverableArtifacts(artifacts), [artifacts])
  const visibleArtifactScrollKey = useMemo(
    () =>
      visibleArtifacts
        .map((artifact) => `${artifact.id}:${artifact.turn_id}:${artifact.updated_at}`)
        .join("|"),
    [visibleArtifacts],
  )

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
  }, [setIsFollowingBottom])

  useEffect(() => {
    if (isFollowingBottom) scrollToBottom()
  }, [isFollowingBottom, scrollToBottom, timeline, visibleArtifactScrollKey])

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
                  <GeneratedFileCards
                    artifacts={visibleArtifacts.filter(
                      (artifact) => artifact.turn_id === entry.turn.id,
                    )}
                    onOpenArtifact={onOpenArtifact}
                  />
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

function GeneratedFileCards({
  artifacts,
  onOpenArtifact,
}: {
  artifacts: AgentRuntimeArtifact[]
  onOpenArtifact?: (artifactId: string) => void
}) {
  const t = useTranslations("agentRuntime")
  const [copiedId, setCopiedId] = useState<string | null>(null)
  if (!artifacts.length) return null

  const copyPath = (artifact: AgentRuntimeArtifact) => {
    const path = artifactFilePath(artifact)
    if (!path) return
    void navigator.clipboard?.writeText(path).then(() => {
      setCopiedId(artifact.id)
      window.setTimeout(() => setCopiedId(null), 1500)
    })
  }

  return (
    <section
      className="mt-3 grid gap-2 rounded-lg border border-border/70 bg-muted/20 p-2.5"
      data-testid="generated-file-cards"
      aria-label={t("artifacts.generatedFiles")}
    >
      <div className="flex items-center gap-2 px-1 text-xs font-medium text-muted-foreground">
        <FileText className="h-3.5 w-3.5" aria-hidden="true" />
        <span>{t("artifacts.generatedFiles")}</span>
      </div>
      <div className="grid gap-2">
        {artifacts.map((artifact) => {
          const path = artifactFilePath(artifact)
          const downloadUrl = path ? buildAgentFsDownloadUrl(path) : null
          const title = artifactDisplayTitle(artifact)
          const typeLabel = artifactTypeLabel(t, artifact.type)
          const subtitle = artifactDisplaySubtitle(artifact, typeLabel)
          const previewLabel = `${t("artifacts.preview")} ${title}`
          return (
            <article
              key={artifact.id}
              className="grid gap-2 rounded-lg border border-border/70 bg-background px-3 py-2.5 shadow-sm shadow-foreground/[0.03] sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
            >
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                    {typeLabel}
                  </span>
                  <h3 className="truncate text-sm font-medium text-foreground">{title}</h3>
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {subtitle}
                </p>
              </div>
              <div className="flex min-w-0 items-center gap-1 justify-self-start sm:justify-self-end">
                <button
                  type="button"
                  className="inline-flex h-8 items-center rounded-md bg-muted/70 px-2.5 text-xs font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => onOpenArtifact?.(artifact.id)}
                  aria-label={previewLabel}
                >
                  {t("artifacts.preview")}
                </button>
                {downloadUrl ? (
                  <a
                    href={downloadUrl}
                    download
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-label={`${t("artifacts.download")} ${title}`}
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                ) : null}
                {path ? (
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    onClick={() => copyPath(artifact)}
                    aria-label={`${t("artifacts.copyPath")} ${title}`}
                  >
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="sr-only">
                      {copiedId === artifact.id
                        ? t("artifacts.pathCopied")
                        : t("artifacts.copyPath")}
                    </span>
                  </button>
                ) : null}
              </div>
            </article>
          )
        })}
      </div>
    </section>
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
      return null
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
