"use client"

import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useLocale, useTranslations } from "next-intl"

import { ActivityDisclosureProvider } from "@/components/bioinfoflow/agent/activity-disclosure"
import { AgentActivityGroup } from "@/components/bioinfoflow/agent/agent-activity"
import { AgentArtifactReference } from "@/components/bioinfoflow/agent/agent-artifact"
import { AgentLiveStatus } from "@/components/bioinfoflow/agent/agent-live-status"
import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import { AgentPlanEntry } from "@/components/bioinfoflow/agent/plan-entry"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Button } from "@/components/ui/button"
import type {
  ConversationInteractionResponse,
  ConversationRunAudit,
  ConversationViewModel,
  MessageTranscriptBlock,
  TranscriptBlock,
} from "@/lib/agent/conversation-model/types"
import {
  dateTimeAttribute,
  formatAbsoluteDateTime,
  formatAgentEndTime,
} from "@/lib/agent/date-format"
import {
  AlertTriangle,
  ArrowDown,
  Check,
  Copy,
} from "@/lib/icons"
import { cn } from "@/lib/utils"

type ConversationTranscriptProps = {
  view: ConversationViewModel
  onRespond?: (
    interactionId: string,
    response: ConversationInteractionResponse,
  ) => void | Promise<void>
  onOpenRun?: (runId: string) => void
  className?: string
}

const BOTTOM_THRESHOLD_PX = 96
const READ_ANCHOR_ATTRIBUTE = "data-agent-read-anchor"

type TranscriptReadAnchor = { id: string; offset: number }

export function ConversationTranscript({
  view,
  onRespond,
  onOpenRun,
  className,
}: ConversationTranscriptProps) {
  const t = useTranslations("agentTranscript")
  const contentRevision = useMemo(
    () =>
      view.transcript
        .map((block) => `${block.id}:${block.type}:${block.createdAt ?? ""}`)
        .join("|"),
    [view.transcript],
  )
  const scrollRef = useRef<HTMLElement>(null)
  const initializedRef = useRef(false)
  const contentRevisionRef = useRef(contentRevision)
  const readAnchorRef = useRef<TranscriptReadAnchor | null>(null)
  const [followingBottom, setFollowingBottom] = useState(true)
  const [hasNewContent, setHasNewContent] = useState(false)
  const activeInteractionBlockId = currentActiveInteractionBlockId(view)
  const copyableMessageIds = useMemo(
    () => completedFinalAssistantMessageIds(view.transcript, view.runs),
    [view.runs, view.transcript],
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
  }, [contentRevision, followingBottom])

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
        className="h-full min-h-0 min-w-0 overflow-x-clip overflow-y-auto px-3 py-5 sm:px-5 sm:py-6"
        data-testid="agent-transcript"
        onScroll={handleScroll}
      >
        <ActivityDisclosureProvider>
          <div
            className="mx-auto grid w-full max-w-[46rem] min-w-0 content-start gap-3"
            data-testid="agent-transcript-content"
          >
            {view.transcript.map((block) => (
              <div
                key={block.id}
                className="min-w-0"
                data-agent-read-anchor={`block:${block.id}`}
              >
                <TranscriptBlockView
                  block={block}
                  onRespond={onRespond}
                  onOpenRun={onOpenRun}
                  activeInteractionBlockId={activeInteractionBlockId}
                  copyableMessageIds={copyableMessageIds}
                />
              </div>
            ))}
            {view.activeWork && view.activeWork.status !== "waiting_user" ? (
              <AgentLiveStatus />
            ) : null}
          </div>
        </ActivityDisclosureProvider>
      </section>

      {hasNewContent ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center px-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="pointer-events-auto rounded-full border-border/60 bg-background/90 px-3 text-muted-foreground shadow-lg shadow-foreground/5 backdrop-blur-md hover:bg-background hover:text-foreground dark:bg-background/90 dark:hover:bg-background motion-reduce:transition-none"
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

function TranscriptBlockView({
  block,
  onRespond,
  onOpenRun,
  activeInteractionBlockId,
  copyableMessageIds,
}: {
  block: TranscriptBlock
  onRespond: ConversationTranscriptProps["onRespond"]
  onOpenRun?: (runId: string) => void
  activeInteractionBlockId: string | null
  copyableMessageIds: ReadonlySet<string>
}) {
  const tHistory = useTranslations("agentHistory")
  const tRun = useTranslations("agentRun")

  switch (block.type) {
    case "message":
      return (
        <ConversationMessage
          block={block}
          copyable={copyableMessageIds.has(block.id)}
          onOpenRun={onOpenRun}
        />
      )
    case "reasoning":
      return (
        <AgentThinking
          reasoning={block}
        />
      )
    case "plan":
      return (
        <AgentPlanEntry plan={block} />
      )
    case "activity_group":
      return <AgentActivityGroup activityGroup={block} />
    case "interaction":
      return (
        <AgentInteractionCard
          interaction={block}
          actionable={block.id === activeInteractionBlockId}
          expired={
            block.status === "pending" &&
            block.id !== activeInteractionBlockId
          }
          onRespond={
            block.id === activeInteractionBlockId && onRespond
              ? (response) => onRespond(block.interactionId, response)
              : undefined
          }
        />
      )
    case "artifact":
      return <AgentArtifactReference artifact={block} />
    case "notice":
      return (
        <section
          role="note"
          className="rounded-[10px] border border-border/60 bg-muted/20 px-3.5 py-3"
        >
          <h2 className="text-sm font-medium">{tHistory("notice.title")}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {knownNoticeCode(block.code)
              ? tHistory(`notice.message.${knownNoticeCode(block.code)}`, {
                  limitSeconds: block.params.limit_seconds ?? "",
                  totalTokens: block.params.total_tokens ?? "",
                  tokenBudget: block.params.token_budget ?? "",
                })
              : block.fallback}
          </p>
        </section>
      )
    case "outcome":
      if (block.status === "completed") return null
      return (
        <div
          className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground"
          data-testid="agent-run-outcome"
        >
          <AlertTriangle
            aria-hidden="true"
            className="size-4 text-error-foreground"
          />
          <span>{tRun(`status.${block.status}`)}</span>
          {block.error?.message ?? block.reason ? (
            <span className="min-w-0 truncate">
              {knownRunErrorCode(block.error?.code ?? block.reason)
                ? tRun(`error.${knownRunErrorCode(block.error?.code ?? block.reason)}`)
                : block.error?.message ?? block.reason}
            </span>
          ) : null}
        </div>
      )
    case "unknown":
      return (
        <section
          role="note"
          className="rounded-[10px] border border-border/60 bg-muted/20 px-3.5 py-3"
          data-original-type={block.originalType}
          data-testid="agent-unknown-transcript-block"
        >
          <h2 className="text-sm font-medium">{tHistory("unknown.title")}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {tHistory(
              `unknown.diagnostic.${knownDiagnosticCode(block.diagnosticCode)}`,
              {
                originalType: block.originalType,
                ...block.diagnosticParams,
              },
            )}
          </p>
        </section>
      )
  }
}

function knownNoticeCode(code: string) {
  return [
    "model_stream_interrupted",
    "model_vision_unsupported",
    "recovery_state_ignored",
    "run_timeout_exceeded",
    "token_budget_exceeded",
    "unknown_tool_effect",
    "user_cancelled",
  ].includes(code)
    ? (code as
        | "model_stream_interrupted"
        | "model_vision_unsupported"
        | "recovery_state_ignored"
        | "run_timeout_exceeded"
        | "token_budget_exceeded"
        | "unknown_tool_effect"
        | "user_cancelled")
    : null
}

function knownRunErrorCode(code: string | null | undefined) {
  return [
    "agent_failed",
    "invalid_plan",
    "iteration_limit",
    "model_attempt_timeout",
    "model_vision_unsupported",
    "no_progress",
    "run_timeout_exceeded",
    "runtime_failed",
    "token_budget_exceeded",
  ].includes(code ?? "")
    ? (code as
        | "agent_failed"
        | "invalid_plan"
        | "iteration_limit"
        | "model_attempt_timeout"
        | "model_vision_unsupported"
        | "no_progress"
        | "run_timeout_exceeded"
        | "runtime_failed"
        | "token_budget_exceeded")
    : null
}

function ConversationMessage({
  block,
  copyable,
  onOpenRun,
}: {
  block: MessageTranscriptBlock
  copyable: boolean
  onOpenRun?: (runId: string) => void
}) {
  const t = useTranslations("agentTranscript")
  const tHistory = useTranslations("agentHistory")
  const locale = useLocale()
  const timestampId = useId()
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  )
  const isUser = block.role === "user"
  const conversational = block.role === "user" || block.role === "assistant"
  const timestamp = conversational
    ? formatAgentEndTime(block.createdAt, locale)
    : null
  const absoluteTimestamp = conversational
    ? formatAbsoluteDateTime(block.createdAt, locale)
    : null

  async function copyMessage() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(block.text)
      setCopyState("copied")
    } catch {
      setCopyState("failed")
    }
  }

  return (
    <article
      className={cn(
        "group/message min-w-0 rounded-[8px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35 [content-visibility:auto] [contain-intrinsic-size:auto_96px]",
        isUser && "ml-auto w-fit max-w-[76%]",
      )}
      aria-describedby={timestamp ? timestampId : undefined}
      data-role={block.role}
      tabIndex={0}
    >
      <div
        className={cn(
          "grid min-w-0 gap-2",
          isUser &&
            "rounded-[12px] border border-border/60 bg-muted/35 px-3.5 py-3",
        )}
      >
        {block.text ? (
          <MarkdownRenderer content={block.text} variant="agent-transcript" />
        ) : null}
        {block.references.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {block.references.map((reference) =>
              reference.kind === "run" && onOpenRun ? (
                <Button
                  key={reference.id}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => onOpenRun(reference.id)}
                >
                  {reference.label}
                </Button>
              ) : (
                <span
                  key={reference.id}
                  className="rounded-[6px] border border-border/60 bg-background/70 px-2 py-1 text-xs text-muted-foreground"
                  title={reference.path ?? undefined}
                >
                  {tHistory(`reference.${reference.kind}`)} · {reference.label}
                </span>
              ),
            )}
          </div>
        ) : null}
      </div>
      {conversational && (block.text || timestamp) ? (
        <footer
          className={cn(
            "mt-1.5 flex min-w-0 items-center gap-1 text-[11px] leading-none text-muted-foreground/65",
            isUser ? "justify-end" : "justify-start",
          )}
        >
          {copyable && block.text ? (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label={t(copyState === "copied" ? "copied" : "copy")}
              className="size-7 text-muted-foreground/65 hover:bg-muted/45 hover:text-foreground"
              onClick={() => void copyMessage()}
            >
              {copyState === "copied" ? (
                <Check aria-hidden="true" />
              ) : (
                <Copy aria-hidden="true" />
              )}
            </Button>
          ) : null}
          {timestamp ? (
            <time
              id={timestampId}
              className="opacity-0 transition-opacity duration-150 group-hover/message:opacity-100 group-focus-within/message:opacity-100 motion-reduce:transition-none"
              dateTime={dateTimeAttribute(block.createdAt)}
              title={absoluteTimestamp ?? timestamp}
              data-testid={
                isUser
                  ? "agent-user-message-timestamp"
                  : "assistant-response-timestamp"
              }
              translate="no"
            >
              {timestamp}
            </time>
          ) : null}
          {copyState === "failed" ? (
            <span role="alert">{t("copy_failed")}</span>
          ) : null}
        </footer>
      ) : null}
    </article>
  )
}

function currentActiveInteractionBlockId(view: ConversationViewModel) {
  if (!view.activeWork || view.activeWork.status !== "waiting_user") return null
  for (let index = view.transcript.length - 1; index >= 0; index -= 1) {
    const block = view.transcript[index]
    if (
      block.type === "interaction" &&
      block.status === "pending" &&
      block.runId === view.activeWork.runId
    ) {
      return block.id
    }
  }
  return null
}

function completedFinalAssistantMessageIds(
  transcript: readonly TranscriptBlock[],
  runs: readonly ConversationRunAudit[],
) {
  const completedRunIds = new Set(
    runs.filter((run) => run.status === "completed").map((run) => run.id),
  )
  const finalMessageByRun = new Map<string, string>()
  for (const block of transcript) {
    if (
      block.type === "message" &&
      block.role === "assistant" &&
      !block.streaming &&
      block.runId &&
      completedRunIds.has(block.runId)
    ) {
      finalMessageByRun.set(block.runId, block.id)
    }
  }
  return new Set(finalMessageByRun.values())
}

function knownDiagnosticCode(code: string) {
  return [
    "event_gap",
    "invalid_payload",
    "unknown_event_type",
    "unsupported_protocol_version",
    "unknown_message_part",
    "orphan_tool_result",
    "unsupported_entry_version",
    "unknown_history_entry",
  ].includes(code)
    ? code
    : "fallback"
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
