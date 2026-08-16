"use client"

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import type { ComponentProps } from "react"
import { useLocale, useTranslations } from "next-intl"

import { ActivityDisclosureProvider } from "@/components/bioinfoflow/agent/activity-disclosure"
import { AgentActivityGroup } from "@/components/bioinfoflow/agent/agent-activity"
import { AgentArtifactReference } from "@/components/bioinfoflow/agent/agent-artifact"
import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import { AgentPlanEntry } from "@/components/bioinfoflow/agent/plan-entry"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Button } from "@/components/ui/button"
import type {
  ActivityGroupTranscriptBlock,
  ArtifactTranscriptBlock,
  ConversationViewModel,
  InteractionTranscriptBlock,
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
  CheckCircle2,
  Copy,
  Loader2,
} from "@/lib/icons"
import { cn } from "@/lib/utils"

type ConversationTranscriptProps = {
  view: ConversationViewModel
  onRespond?: NonNullable<
    ComponentProps<typeof AgentInteractionCard>["onRespond"]
  > extends (response: infer Response) => unknown
    ? (interactionId: string, response: Response) => void | Promise<void>
    : never
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
            className="mx-auto grid w-full max-w-[46rem] min-w-0 content-start gap-5"
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
                />
              </div>
            ))}
            {view.activeWork && view.transcript.length === 0 ? (
              <ActiveWorkIndicator view={view} />
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
}: {
  block: TranscriptBlock
  onRespond: ConversationTranscriptProps["onRespond"]
  onOpenRun?: (runId: string) => void
}) {
  const tHistory = useTranslations("agentHistory")
  const tRun = useTranslations("agentRun")

  switch (block.type) {
    case "message":
      return <ConversationMessage block={block} onOpenRun={onOpenRun} />
    case "reasoning":
      return (
        <AgentThinking
          part={{ id: block.id, type: "reasoning_summary", text: block.text }}
          active={block.streaming}
        />
      )
    case "plan":
      return (
        <AgentPlanEntry
          entry={{
            payload: {
              plan_id: block.planId,
              revision: block.revision,
              title: block.title,
              items: block.items,
              updated_at: block.updatedAt,
            },
          }}
        />
      )
    case "activity_group":
      return <ConversationActivityGroup block={block} />
    case "interaction":
      return (
        <ConversationInteraction block={block} onRespond={onRespond} />
      )
    case "artifact":
      return <ConversationArtifact block={block} />
    case "notice":
      return (
        <section
          role="note"
          className="rounded-[10px] border border-border/60 bg-muted/20 px-3.5 py-3"
        >
          <h2 className="text-sm font-medium">{tHistory("notice.title")}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {block.message}
          </p>
        </section>
      )
    case "outcome":
      return (
        <div
          className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground"
          data-testid="agent-run-outcome"
        >
          {block.status === "completed" ? (
            <CheckCircle2 aria-hidden="true" className="size-4 text-success-foreground" />
          ) : (
            <AlertTriangle aria-hidden="true" className="size-4 text-error-foreground" />
          )}
          <span>{tRun(`status.${block.status}`)}</span>
          {block.error?.message ?? block.reason ? (
            <span className="min-w-0 truncate">
              {block.error?.message ?? block.reason}
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
            {block.message}
          </p>
        </section>
      )
  }
}

function ConversationMessage({
  block,
  onOpenRun,
}: {
  block: MessageTranscriptBlock
  onOpenRun?: (runId: string) => void
}) {
  const t = useTranslations("agentTranscript")
  const tHistory = useTranslations("agentHistory")
  const locale = useLocale()
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
        "min-w-0 [content-visibility:auto] [contain-intrinsic-size:auto_96px]",
        isUser && "ml-auto w-fit max-w-[76%]",
      )}
      data-role={block.role}
    >
      <div
        className={cn(
          "grid min-w-0 gap-2",
          isUser &&
            "rounded-[12px] border border-border/60 bg-muted/35 px-3.5 py-3",
        )}
      >
        {block.text ? <MarkdownRenderer content={block.text} /> : null}
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
          {block.text ? (
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

function ConversationActivityGroup({
  block,
}: {
  block: ActivityGroupTranscriptBlock
}) {
  type Tool = ComponentProps<typeof AgentActivityGroup>["tools"][number]
  const tools: Tool[] = block.activities.map((activity) => ({
    call_id: activity.callId,
    group_id: block.id,
    execution_mode: block.executionMode,
    name: activity.name,
    display_name: activity.displayName,
    category: activityCategory(activity.category),
    summary: activity.summary,
    arguments: jsonObject(activity.input),
    status: activity.status,
    revision: 0,
    started_at: activity.startedAt,
    completed_at: activity.completedAt,
    input_summary: null,
    output_summary: stringValue(activity.output),
    error: activity.error,
    public_details: activityDetails(activity),
  }))
  return (
    <AgentActivityGroup
      tools={tools}
      executionMode={block.executionMode}
    />
  )
}

function ConversationInteraction({
  block,
  onRespond,
}: {
  block: InteractionTranscriptBlock
  onRespond: ConversationTranscriptProps["onRespond"]
}) {
  type InteractionProps = ComponentProps<typeof AgentInteractionCard>
  if (!isInteractionRequest(block.request)) {
    return (
      <section
        role="note"
        className="rounded-[10px] border border-border/60 bg-muted/20 px-3.5 py-3 text-sm text-muted-foreground"
        data-testid="agent-unknown-transcript-block"
      >
        Unsupported interaction content
      </section>
    )
  }
  return (
    <AgentInteractionCard
      interactionId={block.interactionId}
      request={block.request as InteractionProps["request"]}
      response={block.response as InteractionProps["response"]}
      onRespond={
        block.status === "pending" && onRespond
          ? (response) => onRespond(block.interactionId, response)
          : undefined
      }
    />
  )
}

function ConversationArtifact({ block }: { block: ArtifactTranscriptBlock }) {
  type ArtifactPart = ComponentProps<typeof AgentArtifactReference>["part"]
  const part: ArtifactPart = {
    id: block.id,
    type: "artifact_ref",
    artifact_id: block.artifactId,
    title: block.title,
    media_type: block.mediaType,
  }
  return <AgentArtifactReference part={part} />
}

function ActiveWorkIndicator({ view }: { view: ConversationViewModel }) {
  const t = useTranslations("agentRun")
  const activeWork = view.activeWork
  if (!activeWork) return null
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex min-h-10 items-center gap-2 text-sm text-muted-foreground"
    >
      <Loader2
        aria-hidden="true"
        className="size-4 animate-spin motion-reduce:animate-none"
      />
      <span>
        {activeWork.phase
          ? t(`phase.${activeWork.phase}`)
          : t(`status.${activeWork.status}`)}
      </span>
    </div>
  )
}

function activityDetails(
  activity: ActivityGroupTranscriptBlock["activities"][number],
) {
  return [
    activity.input === null || activity.input === undefined
      ? null
      : {
          id: `${activity.id}:input`,
          kind: "input" as const,
          label: null,
          value: stringValue(activity.input) ?? "",
          format: "json" as const,
          copyable: true,
          truncated: false,
          redacted: false,
        },
    activity.output === null || activity.output === undefined
      ? null
      : {
          id: `${activity.id}:output`,
          kind: "output" as const,
          label: null,
          value: stringValue(activity.output) ?? "",
          format: "text" as const,
          copyable: true,
          truncated: false,
          redacted: false,
        },
    activity.error
      ? {
          id: `${activity.id}:error`,
          kind: "error" as const,
          label: null,
          value: activity.error,
          format: "text" as const,
          copyable: true,
          truncated: false,
          redacted: false,
        }
      : null,
  ].filter((detail) => detail !== null)
}

function activityCategory(value: string) {
  const categories = new Set([
    "read",
    "search",
    "command",
    "edit",
    "write",
    "workflow",
    "plan",
    "interaction",
    "other",
  ])
  return (categories.has(value) ? value : "other") as ComponentProps<
    typeof AgentActivityGroup
  >["tools"][number]["category"]
}

function jsonObject(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, never>)
    : {}
}

function stringValue(value: unknown) {
  if (value === null || value === undefined) return null
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function isInteractionRequest(value: unknown): value is { type: string } {
  if (!value || typeof value !== "object") return false
  const type = (value as { type?: unknown }).type
  return type === "approval" || type === "ask_user" || type === "recovery"
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
