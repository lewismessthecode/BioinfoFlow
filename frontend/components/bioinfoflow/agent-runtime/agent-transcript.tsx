"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  AlertTriangle,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Copy,
  Loader2,
  RotateCcw,
} from "@/lib/icons"
import { useLocale, useTranslations } from "next-intl"

import { ScrollToBottom } from "@/components/bioinfoflow/chat/scroll-to-bottom"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type {
  AgentRuntimeSource,
  AgentRuntimeTimelineEntry,
  AgentRuntimeTranscriptSegment,
  AgentRuntimeTurn,
  AgentRuntimeWorkflowRefPart,
} from "@/lib/agent-runtime"
import { agentRuntimeAttachmentPreviewUrl } from "@/lib/agent-runtime"
import {
  dateTimeAttribute,
  formatAbsoluteDateTime,
  formatTranscriptMessageDateTime,
} from "@/lib/agent-runtime/date-format"
import { cn } from "@/lib/utils"
import { ActivityGroup } from "./activity-group"
import {
  SourceCitation,
  SourceEvidenceFooter,
  SourcesDrawer,
} from "./agent-sources"
import { InlineApprovalCard } from "./inline-approval-card"
import type { AgentDecisionHandler, AgentRetryHandler } from "./types"
import { AttachmentPreviewDialog } from "./attachment-preview-dialog"
import type { AgentComposerAttachment } from "./attachment-strip"

const BOTTOM_FOLLOW_THRESHOLD = 80
const TEXT_SWAP_DURATION_MS = 150

export function AgentTranscript({
  timeline,
  onDecision,
  onRetryTurn,
  responseActionsBusy = false,
  eventWindowLimited = false,
}: {
  timeline: AgentRuntimeTimelineEntry[]
  onDecision?: AgentDecisionHandler
  onRetryTurn?: AgentRetryHandler
  responseActionsBusy?: boolean
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
                <UserMessageBubble turn={entry.turn} />
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
                      busy={responseActionsBusy}
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

function UserMessageBubble({ turn }: { turn: AgentRuntimeTurn }) {
  const t = useTranslations("agentRuntime.attachments")
  const locale = useLocale()
  const [now] = useState(() => new Date())
  const [previewAttachment, setPreviewAttachment] =
    useState<AgentComposerAttachment | null>(null)
  const displayParts = userMessageDisplayPartsForTurn(turn)
  const imageAttachments = userMessageImageAttachments(turn, t("imageLabel"))
  const timestamp = formatTranscriptMessageDateTime(turn.created_at, locale, now)
  const absoluteTimestamp = formatAbsoluteDateTime(turn.created_at, locale)
  const timestampDateTime = dateTimeAttribute(turn.created_at)

  return (
    <div
      className="flex min-w-0 max-w-[76%] flex-col items-end gap-1.5"
      data-testid="agent-user-message-shell"
    >
      <div
        className="max-w-full rounded-lg border border-border/60 bg-muted/35 px-3.5 py-2.5 text-[15px] leading-6 text-foreground shadow-none"
        data-testid="agent-user-message"
      >
        {imageAttachments.length ? (
          <div className="mb-2 flex max-w-full gap-2 overflow-x-auto">
            {imageAttachments.map((attachment) => (
              <button
                key={attachment.id}
                type="button"
                className="shrink-0 rounded-lg border border-border bg-background/70 p-1 transition-colors hover:bg-background"
                onClick={() => setPreviewAttachment(attachment)}
                aria-label={t("previewImage")}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- private authenticated preview URL */}
                <img
                  src={attachment.previewUrl || ""}
                  alt={attachment.filename}
                  className="h-20 w-24 rounded-md object-cover"
                />
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1">
          {displayParts.map((part) =>
            part.type === "text" ? (
              <span
                key={part.key}
                className="min-w-0 whitespace-pre-wrap break-words"
              >
                {part.text}
              </span>
            ) : (
              <UserMessageTokenSpan key={part.key} token={part} />
            ),
          )}
        </div>
      </div>
      {timestamp ? (
        <time
          dateTime={timestampDateTime ?? undefined}
          title={absoluteTimestamp ?? timestamp}
          className="block px-0.5 text-right text-[11px] font-normal leading-none text-muted-foreground/64"
          data-testid="agent-user-message-timestamp"
          suppressHydrationWarning
        >
          {timestamp}
        </time>
      ) : null}
      <AttachmentPreviewDialog
        open={Boolean(previewAttachment)}
        attachment={previewAttachment}
        onOpenChange={(open) => {
          if (!open) setPreviewAttachment(null)
        }}
        readOnly
      />
    </div>
  )
}

function userMessageImageAttachments(
  turn: AgentRuntimeTurn,
  filename: string,
): AgentComposerAttachment[] {
  return (turn.input_parts ?? []).flatMap((part) => {
    if (!("type" in part) || part.type !== "image_ref") return []
    return [
      {
        id: part.attachment_id,
        filename,
        kind: "image" as const,
        status: "ready" as const,
        previewUrl: agentRuntimeAttachmentPreviewUrl(part.attachment_id),
      },
    ]
  })
}

function UserMessageTokenSpan({ token }: { token: UserMessageToken }) {
  return (
    <span
      className="inline-flex min-h-6 max-w-full items-center gap-1 rounded-[6px] border border-border/60 bg-background/70 px-1.5 py-0.5 text-[12px] font-medium leading-4 text-foreground/78"
      data-token-kind={token.kind}
    >
      <span className="min-w-0 truncate" translate="no">{token.label}</span>
      {token.version ? (
        <span
          className="shrink-0 text-[10px] font-normal leading-none text-muted-foreground/78"
          title={token.title}
          translate="no"
        >
          {token.version}
        </span>
      ) : null}
    </span>
  )
}

type UserMessageToken = {
  type: "token"
  key: string
  kind: "skill" | "workflow" | "file" | "directory" | "run"
  label: string
  version?: string | null
  title?: string
}

type UserMessageTextPart = {
  type: "text"
  key: string
  text: string
}

type UserMessageDisplayPart = UserMessageTextPart | UserMessageToken

type WorkflowDisplayMetadata = {
  workflow_id?: string | null
  project_id?: string | null
  scope?: "project" | "global"
  name: string
  version?: string | null
}

function userMessageDisplayPartsForTurn(turn: AgentRuntimeTurn): UserMessageDisplayPart[] {
  const inlineParts = userMessageInlinePartsFromTurn(turn)
  if (inlineParts.length) return inlineParts
  return [
    ...userMessageTokensForTurn(turn),
    {
      type: "text",
      key: "text:fallback",
      text: turn.input_text,
    },
  ]
}

function userMessageTokensForTurn(turn: AgentRuntimeTurn): UserMessageToken[] {
  const workflowDisplays = workflowDisplayMetadataFromTurn(turn)
  const workflowTokens = (turn.input_parts ?? [])
    .map((part, index) =>
      workflowTokenForInputPart(part, index, workflowDisplays),
    )
    .filter((token): token is UserMessageToken => Boolean(token))
  const skillTokens = Array.from(new Set(turn.active_skill_names ?? []))
    .filter((name) => name.trim().length > 0)
    .map((name) => ({
      type: "token" as const,
      key: `skill:${name}`,
      kind: "skill" as const,
      label: `/${name}`,
    }))
  return [...workflowTokens, ...skillTokens]
}

function workflowTokenForInputPart(
  part: NonNullable<AgentRuntimeTurn["input_parts"]>[number],
  index: number,
  workflowDisplays: WorkflowDisplayMetadata[],
): UserMessageToken | null {
  if (!("kind" in part) || part.kind !== "workflow_ref") return null
  const display = workflowDisplayForPart(part, workflowDisplays)
  const name = display?.name || "workflow"
  const version = display?.version?.trim() || null
  return {
    type: "token",
    key: `workflow:${part.workflow_id ?? part.project_id ?? part.scope ?? index}:${index}`,
    kind: "workflow",
    label: `@${name}`,
    version,
    title: version ? `${name} ${version}` : undefined,
  }
}

function userMessageInlinePartsFromTurn(turn: AgentRuntimeTurn): UserMessageDisplayPart[] {
  const metadata = turn.model_profile_snapshot?.metadata
  if (!isRecord(metadata)) return []
  return userMessageInlinePartsFromInputDisplay(metadata.input_display)
}

function userMessageInlinePartsFromInputDisplay(
  inputDisplay: unknown,
): UserMessageDisplayPart[] {
  if (!isRecord(inputDisplay)) return []
  const inlineParts = inputDisplay.inline_parts
  if (!Array.isArray(inlineParts)) return []
  return inlineParts.flatMap((item, index) => userMessageInlinePart(item, index))
}

function userMessageInlinePart(item: unknown, index: number): UserMessageDisplayPart[] {
  if (!isRecord(item) || typeof item.type !== "string") return []
  if (item.type === "text") {
    return typeof item.text === "string" && item.text
      ? [{ type: "text", key: `inline-text:${index}`, text: item.text }]
      : []
  }
  if (item.type === "skill") {
    if (typeof item.name !== "string" || !item.name.trim()) return []
    const name = item.name.trim()
    return [
      {
        type: "token",
        key: `inline-skill:${name}:${index}`,
        kind: "skill",
        label: `/${name}`,
      },
    ]
  }
  if (item.type === "context") {
    if (
      typeof item.label !== "string" ||
      !item.label.trim() ||
      !["file", "directory", "workflow", "run"].includes(String(item.kind))
    ) {
      return []
    }
    return [
      {
        type: "token",
        key: `inline-context:${nullableString(item.id) ?? index}:${index}`,
        kind: item.kind as UserMessageToken["kind"],
        label: `@${item.label.trim()}`,
        title: nullableString(item.detail) ?? undefined,
      },
    ]
  }
  if (item.type !== "workflow" || typeof item.name !== "string" || !item.name.trim()) {
    return []
  }
  const name = item.name.trim()
  const version = nullableString(item.version)?.trim() || null
  return [
    {
      type: "token",
      key: `inline-workflow:${nullableString(item.workflow_id) ?? nullableString(item.project_id) ?? index}:${index}`,
      kind: "workflow",
      label: `@${name}`,
      version,
      title: version ? `${name} ${version}` : undefined,
    },
  ]
}

function workflowDisplayForPart(
  part: AgentRuntimeWorkflowRefPart,
  workflowDisplays: WorkflowDisplayMetadata[],
): WorkflowDisplayMetadata | null {
  const directName = part.display_name?.trim()
  if (directName) {
    return {
      workflow_id: part.workflow_id ?? null,
      project_id: part.project_id ?? null,
      scope: part.scope,
      name: directName,
      version: part.display_version?.trim() || null,
    }
  }
  return workflowDisplays.find((display) => workflowDisplayMatchesPart(display, part)) ?? null
}

function workflowDisplayMatchesPart(
  display: WorkflowDisplayMetadata,
  part: AgentRuntimeWorkflowRefPart,
) {
  if (part.workflow_id && display.workflow_id === part.workflow_id) return true
  if (part.workflow_id) return false
  if (display.workflow_id) return false
  const partProjectId = part.project_id ?? null
  const displayProjectId = display.project_id ?? null
  const scopeMatches = part.scope ? display.scope === part.scope : true
  return displayProjectId === partProjectId && scopeMatches
}

function workflowDisplayMetadataFromTurn(
  turn: AgentRuntimeTurn,
): WorkflowDisplayMetadata[] {
  const metadata = turn.model_profile_snapshot?.metadata
  if (!isRecord(metadata)) return []
  const inputDisplay = metadata.input_display
  if (!isRecord(inputDisplay)) return []
  const workflowMentions = inputDisplay.workflow_mentions
  if (!Array.isArray(workflowMentions)) return []
  return workflowMentions.flatMap((item) => {
    if (!isRecord(item) || typeof item.name !== "string" || !item.name.trim()) {
      return []
    }
    return [
      {
        workflow_id: nullableString(item.workflow_id),
        project_id: nullableString(item.project_id),
        scope: item.scope === "project" || item.scope === "global" ? item.scope : undefined,
        name: item.name.trim(),
        version: nullableString(item.version),
      },
    ]
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null
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
    case "user_steer": {
      const displayParts = userMessageInlinePartsFromInputDisplay(
        segment.steer.inputDisplay,
      )
      return (
        <div className="flex justify-end" data-testid="agent-user-steer-shell">
          <div
            className="flex max-w-[76%] flex-col items-end gap-1.5"
            data-testid="agent-user-steer"
          >
            <div className="max-w-full rounded-lg border border-border/60 bg-muted/35 px-3.5 py-2.5 text-[15px] leading-6 text-foreground">
              <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1">
                {(displayParts.length
                  ? displayParts
                  : [
                      {
                        type: "text" as const,
                        key: "steer-text:fallback",
                        text: segment.steer.text,
                      },
                    ]
                ).map((part) =>
                  part.type === "text" ? (
                    <span
                      key={part.key}
                      className="min-w-0 whitespace-pre-wrap break-words"
                    >
                      {part.text}
                    </span>
                  ) : (
                    <UserMessageTokenSpan key={part.key} token={part} />
                  ),
                )}
              </div>
            </div>
            {segment.steer.status !== "delivered" ? (
              <span className="px-0.5 text-right text-[11px] leading-4 text-muted-foreground/70">
                {t(`steer.${segment.steer.status}`)}
              </span>
            ) : null}
          </div>
        </div>
      )
    }
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
    <div className="min-w-0 max-w-full">
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
  busy,
}: {
  text: string
  turn: AgentRuntimeTurn
  onRetryTurn?: AgentRetryHandler
  busy: boolean
}) {
  const t = useTranslations("agentRuntime")
  const locale = useLocale()
  const [now] = useState(() => new Date())
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle")
  const copyResetTimerRef = useRef<number | null>(null)
  const copyLabel = t("responseActions.copy")
  const copiedLabel = t("responseActions.copied")
  const copyFailedLabel = t("responseActions.copyFailed")
  const retryLabel = t("responseActions.retry")
  const retryingLabel = t("responseActions.retrying")
  const completedAt = turn.completed_at ?? turn.updated_at
  const timestamp = formatTranscriptMessageDateTime(completedAt, locale, now)
  const absoluteTimestamp = formatAbsoluteDateTime(completedAt, locale)
  const timestampDateTime = dateTimeAttribute(completedAt)

  useEffect(() => {
    return () => {
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current)
      }
    }
  }, [])

  const copyResponse = useCallback(async () => {
    const copied = await copyTextToClipboard(text)
    setCopyState(copied ? "copied" : "failed")
    if (copyResetTimerRef.current !== null) {
      window.clearTimeout(copyResetTimerRef.current)
    }
    copyResetTimerRef.current = window.setTimeout(() => {
      setCopyState("idle")
      copyResetTimerRef.current = null
    }, 1800)
  }, [text])
  const currentCopyLabel =
    copyState === "copied"
      ? copiedLabel
      : copyState === "failed"
        ? copyFailedLabel
        : copyLabel
  const currentRetryLabel = busy ? retryingLabel : retryLabel

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
            aria-label={currentCopyLabel}
            title={currentCopyLabel}
            onClick={() => void copyResponse()}
          >
            {copyState === "copied" ? (
              <Check className="h-3.5 w-3.5" />
            ) : copyState === "failed" ? (
              <AlertTriangle className="h-3.5 w-3.5" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">{currentCopyLabel}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-40"
            aria-label={currentRetryLabel}
            title={currentRetryLabel}
            aria-busy={busy}
            disabled={!onRetryTurn || busy}
            onClick={() => onRetryTurn?.(turn)}
          >
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">{currentRetryLabel}</TooltipContent>
      </Tooltip>
      {timestamp ? (
        <time
          dateTime={timestampDateTime ?? undefined}
          title={absoluteTimestamp ?? timestamp}
          className="ml-1 text-[11px] leading-none text-muted-foreground/64"
          data-testid="assistant-response-timestamp"
          suppressHydrationWarning
        >
          {timestamp}
        </time>
      ) : null}
    </div>
  )
}

async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Self-hosted HTTP origins and browser policies can reject the async API.
  }

  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.readOnly = true
  textarea.dataset.agentCopyFallback = ""
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  textarea.style.pointerEvents = "none"
  document.body.appendChild(textarea)
  textarea.select()
  textarea.setSelectionRange(0, text.length)
  try {
    return document.execCommand?.("copy") === true
  } catch {
    return false
  } finally {
    textarea.remove()
  }
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
