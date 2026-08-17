"use client"

import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useMediaQuery } from "@/hooks/use-media-query"
import { useAgentTrace } from "@/hooks/use-agent-trace"
import type {
  AgentTraceCategory,
  AgentTraceContextSnapshot,
  AgentTraceEvent,
  AgentTraceEventDetail,
  AgentTracePhase,
  AgentTraceViewModel,
  TraceJsonValue,
} from "@/lib/agent/trace-model/types"
import {
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDashed,
  Loader2,
  X,
} from "@/lib/icons"
import { cn } from "@/lib/utils"

type AgentTraceViewProps = {
  view: AgentTraceViewModel
  onLoadDetail: (eventId: string) => Promise<AgentTraceEventDetail>
}

const INSPECTOR_TABS = [
  "summary",
  "payload",
  "result",
  "schema",
  "timing",
] as const

type InspectorTab = (typeof INSPECTOR_TABS)[number]

const TRACE_CATEGORY_STYLES: Record<
  AgentTraceCategory,
  { context: string; badge: string; dot: string }
> = {
  system: {
    context: "bg-foreground/50",
    badge: "bg-foreground/[0.08] text-foreground/65",
    dot: "bg-foreground/55",
  },
  user: {
    context: "bg-[var(--brand-accent)]/75",
    badge: "bg-[var(--brand-accent-muted)] text-[var(--brand-accent)]",
    dot: "bg-[var(--brand-accent)]",
  },
  context: {
    context: "bg-warning/65",
    badge: "bg-warning-muted text-warning",
    dot: "bg-warning",
  },
  assistant: {
    context: "bg-success/70",
    badge: "bg-success-muted text-success-foreground",
    dot: "bg-success",
  },
  tool: {
    context: "bg-info/65",
    badge: "bg-info-muted text-info",
    dot: "bg-info",
  },
  unknown: {
    context: "bg-muted-foreground/45",
    badge: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
  },
}

const TRACE_STATUS_KEYS = {
  completed: "completed",
  ready: "ready",
  received: "received",
  success: "success",
  running: "running",
  pending: "pending",
  queued: "queued",
  failed: "failed",
  error: "error",
  cancelled: "cancelled",
  blocked: "blocked",
} as const

const INLINE_INSPECTOR_MIN_WIDTH = 960

export function AgentTraceView({ view, onLoadDetail }: AgentTraceViewProps) {
  const t = useTranslations("agentTrace")
  const viewportSupportsInlineInspector = useMediaQuery("(min-width: 1280px)")
  const traceRootRef = useRef<HTMLElement | null>(null)
  const [containerSupportsInlineInspector, setContainerSupportsInlineInspector] =
    useState<boolean | null>(null)
  const detailCache = useRef(new Map<string, AgentTraceEventDetail>())
  const detailRequest = useRef(0)
  const [selectedEvent, setSelectedEvent] = useState<AgentTraceEvent | null>(
    null,
  )
  const [detail, setDetail] = useState<AgentTraceEventDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const [expandedEventIds, setExpandedEventIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [playheadSequence, setPlayheadSequence] = useState<number | null>(null)

  const events = useMemo(
    () => view.turns.flatMap((turn) => turn.events),
    [view.turns],
  )
  const maxSequence = events.at(-1)?.sequence ?? 0
  const visiblePlayheadSequence = playheadSequence ?? maxSequence
  const isInspectorInline =
    containerSupportsInlineInspector ?? viewportSupportsInlineInspector

  useEffect(() => {
    const element = traceRootRef.current
    if (!element || typeof ResizeObserver === "undefined") {
      setContainerSupportsInlineInspector(null)
      return
    }

    const update = (width: number) => {
      setContainerSupportsInlineInspector(width >= INLINE_INSPECTOR_MIN_WIDTH)
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) update(entry.contentRect.width)
    })
    observer.observe(element)
    update(element.getBoundingClientRect().width)
    return () => observer.disconnect()
  }, [])

  async function loadEventDetail(
    event: AgentTraceEvent,
    { bypassCache = false }: { bypassCache?: boolean } = {},
  ) {
    setDetailError(false)
    const cached = detailCache.current.get(event.id)
    if (cached && !bypassCache) {
      setDetail(cached)
      setDetailLoading(false)
      return
    }

    const request = detailRequest.current + 1
    detailRequest.current = request
    setDetail(null)
    setDetailLoading(true)
    try {
      const loaded = await onLoadDetail(event.id)
      if (detailRequest.current !== request) return
      detailCache.current.set(event.id, loaded)
      setDetail(loaded)
    } catch {
      if (detailRequest.current === request) setDetailError(true)
    } finally {
      if (detailRequest.current === request) setDetailLoading(false)
    }
  }

  function selectEvent(event: AgentTraceEvent) {
    if (event.category === "assistant" || event.category === "tool") {
      setPlayheadSequence(event.sequence)
    }
    if (!event.hasDetail) return

    setSelectedEvent(event)
    void loadEventDetail(event)
  }

  function closeInspector() {
    detailRequest.current += 1
    setSelectedEvent(null)
    setDetail(null)
    setDetailLoading(false)
    setDetailError(false)
  }

  function toggleExpanded(eventId: string) {
    setExpandedEventIds((current) => {
      const next = new Set(current)
      if (next.has(eventId)) next.delete(eventId)
      else next.add(eventId)
      return next
    })
  }

  const inspector = selectedEvent ? (
    <TraceInspector
      event={selectedEvent}
      detail={detail}
      loading={detailLoading}
      error={detailError}
      onClose={closeInspector}
      onRetry={() => void loadEventDetail(selectedEvent, { bypassCache: true })}
    />
  ) : null

  return (
    <section
      ref={traceRootRef}
      className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-background"
      aria-label={t("title")}
      data-testid="agent-trace-view"
    >
      <TraceContextFlow
        snapshots={view.contextFlow}
        turns={view.turns.map((turn) => ({ id: turn.id, index: turn.index }))}
        playheadSequence={visiblePlayheadSequence}
        onSelectSnapshot={setPlayheadSequence}
      />

      <div
        className={cn(
          "grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)]",
          isInspectorInline && "grid-cols-[minmax(0,1fr)_auto]",
        )}
      >
        <TraceTimeline
          view={view}
          selectedEventId={selectedEvent?.id ?? null}
          expandedEventIds={expandedEventIds}
          onSelectEvent={(event) => void selectEvent(event)}
          onToggleExpanded={toggleExpanded}
        />

        {isInspectorInline && inspector ? (
          <aside
            className="flex min-h-0 w-[306px] flex-col border-l border-border/70 bg-background"
            aria-label={t("inspector.label")}
            role="complementary"
          >
            {inspector}
          </aside>
        ) : null}
      </div>

      {!isInspectorInline ? (
        <Sheet
          open={selectedEvent !== null}
          onOpenChange={(open) => {
            if (!open) closeInspector()
          }}
        >
          <SheetContent
            side="right"
            closeLabel={t("inspector.close")}
            showCloseButton={false}
            className="w-[min(92vw,24rem)] max-w-none gap-0 overscroll-contain overflow-hidden p-0 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] sm:max-w-[24rem]"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>{t("inspector.label")}</SheetTitle>
              <SheetDescription>
                {selectedEvent?.title ?? t("inspector.label")}
              </SheetDescription>
            </SheetHeader>
            {inspector}
          </SheetContent>
        </Sheet>
      ) : null}
    </section>
  )
}

function TraceContextFlow({
  snapshots,
  turns,
  playheadSequence,
  onSelectSnapshot,
}: {
  snapshots: AgentTraceContextSnapshot[]
  turns: Array<{ id: string; index: number }>
  playheadSequence: number
  onSelectSnapshot: (sequence: number) => void
}) {
  const t = useTranslations("agentTrace")
  const turnIndex = new Map(turns.map((turn) => [turn.id, turn.index]))
  const snapshot = snapshotAtSequence(snapshots, playheadSequence)
  const snapshotWeights = snapshots.map(snapshotWeight)
  const totalWeight = snapshotWeights.reduce((sum, weight) => sum + weight, 0)
  const selectedSnapshotIndex = snapshot
    ? snapshots.findIndex((item) => item.id === snapshot.id)
    : -1
  const selectedWeight = snapshotWeights
    .slice(0, selectedSnapshotIndex + 1)
    .reduce((sum, weight) => sum + weight, 0)
  const playheadPercent =
    totalWeight > 0 ? (selectedWeight / totalWeight) * 100 : 100
  const compactNumber = (value: number) =>
    formatCompactNumber(value, (formatted) =>
      t("units.thousand", { value: formatted }),
    )

  return (
    <section
      className="shrink-0 border-b border-border/70 px-[22px] pb-2 pt-2.5"
      aria-label={t("contextFlow.label")}
      role="region"
    >
      <div className="mb-[7px] flex min-w-0 items-center justify-between gap-3 text-[11px] text-muted-foreground">
        <span className="font-medium text-foreground/72">
          {t("contextFlow.title")}
        </span>
        <span
          className="flex min-w-0 items-center gap-2 overflow-x-auto whitespace-nowrap tabular-nums [scrollbar-width:none]"
          translate="no"
        >
          {snapshot?.inputTokens !== null && snapshot?.inputTokens !== undefined ? (
            <span className="font-medium text-foreground/72">
              {t("contextFlow.usage.input", {
                count: compactNumber(snapshot.inputTokens),
              })}
            </span>
          ) : null}
          {snapshot?.outputTokens !== null && snapshot?.outputTokens !== undefined ? (
            <span>
              {t("contextFlow.usage.output", {
                count: compactNumber(snapshot.outputTokens),
              })}
            </span>
          ) : null}
          {snapshot?.cachedInputTokens !== null &&
          snapshot?.cachedInputTokens !== undefined ? (
            <span>
              {t("contextFlow.cached", {
                count: compactNumber(snapshot.cachedInputTokens),
              })}
            </span>
          ) : null}
          {snapshot?.reasoningTokens !== null &&
          snapshot?.reasoningTokens !== undefined ? (
            <span>
              {t("contextFlow.usage.reasoning", {
                count: compactNumber(snapshot.reasoningTokens),
              })}
            </span>
          ) : null}
          {snapshot?.totalTokens !== null && snapshot?.totalTokens !== undefined ? (
            <span>
              {t("contextFlow.usage.total", {
                count: compactNumber(snapshot.totalTokens),
              })}
            </span>
          ) : null}
          {snapshot?.maxContextTokens !== null &&
          snapshot?.maxContextTokens !== undefined ? (
            <span className="text-muted-foreground/70">
              {t("contextFlow.capacity", {
                count: compactNumber(snapshot.maxContextTokens),
              })}
            </span>
          ) : null}
        </span>
      </div>

      <div className="relative pt-[15px]">
        <div className="absolute inset-x-0 top-0 flex text-[9px] font-medium text-muted-foreground/65">
          {snapshots.map((item, index) => (
            <span
              key={item.id}
              className="min-w-0 basis-0 truncate px-1"
              style={{ flexGrow: snapshotWeights[index] }}
            >
              {t("turn", { index: turnIndex.get(item.turnId) ?? "" })}
            </span>
          ))}
        </div>
        <div className="relative flex h-[30px] min-w-0 gap-px overflow-hidden rounded-[8px] bg-muted/65 p-[3px] ring-1 ring-border/60">
          {snapshots.length > 0 ? (
            snapshots.map((item, index) => (
              <ContextSnapshotSegment
                key={item.id}
                snapshot={item}
                weight={snapshotWeights[index]}
                selected={item.id === snapshot?.id}
                onSelect={() => onSelectSnapshot(item.sequence)}
              />
            ))
          ) : (
            <div className="h-full flex-1 rounded-[4px] bg-muted/70" />
          )}
        </div>
        <div
          className="pointer-events-none absolute bottom-[-4px] top-[13px] left-0 rounded-l-[6px] border border-r-0 border-foreground/18 bg-foreground/[0.025] transition-[width] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
          style={{ width: `${playheadPercent}%` }}
          aria-hidden="true"
        />
        <div
          className="pointer-events-none absolute bottom-[-5px] top-[11px] w-px bg-foreground/45 transition-[left] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
          style={{ left: `${playheadPercent}%` }}
          aria-hidden="true"
        />
      </div>
    </section>
  )
}

function ContextSnapshotSegment({
  snapshot,
  weight,
  selected,
  onSelect,
}: {
  snapshot: AgentTraceContextSnapshot
  weight: number
  selected: boolean
  onSelect: () => void
}) {
  const t = useTranslations("agentTrace")
  const hasCompleteTokenWeights = snapshot.composition.every(
    (item) => item.tokens !== null,
  )
  const weights = snapshot.composition.map((item) =>
    hasCompleteTokenWeights ? item.tokens! : item.characters,
  )
  const totalWeight = weights.reduce((sum, weight) => sum + weight, 0)
  const cachedPercent =
    snapshot.inputTokens !== null &&
    snapshot.cachedInputTokens !== null &&
    snapshot.inputTokens > 0
      ? Math.min(100, (snapshot.cachedInputTokens / snapshot.inputTokens) * 100)
      : null

  return (
    <button
      type="button"
      className={cn(
        "group/context relative flex min-w-px basis-0 overflow-hidden rounded-[4px] outline-none transition-[opacity,transform] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] hover:-translate-y-px focus-visible:ring-2 focus-visible:ring-ring/50 motion-reduce:transition-none",
        snapshot.compacted && "opacity-45",
      )}
      style={{ flexGrow: weight }}
      onClick={onSelect}
      aria-label={t("contextFlow.snapshot", { id: snapshot.id })}
      aria-current={selected ? "true" : undefined}
    >
      {snapshot.composition.map((item, index) => (
        <span
          key={`${snapshot.id}:${item.category}:${index}`}
          className={cn(
            "h-full min-w-px",
            TRACE_CATEGORY_STYLES[item.category].context,
          )}
          style={{
            flexGrow: totalWeight > 0 ? weights[index] : 1,
          }}
          aria-hidden="true"
        />
      ))}
      {cachedPercent !== null && cachedPercent > 0 ? (
        <span
          className="pointer-events-none absolute inset-y-0 left-0 border-r border-foreground/20 bg-foreground/[0.08]"
          style={{ width: `${cachedPercent}%` }}
          aria-hidden="true"
        />
      ) : null}
    </button>
  )
}

function TraceTimeline({
  view,
  selectedEventId,
  expandedEventIds,
  onSelectEvent,
  onToggleExpanded,
}: {
  view: AgentTraceViewModel
  selectedEventId: string | null
  expandedEventIds: ReadonlySet<string>
  onSelectEvent: (event: AgentTraceEvent) => void
  onToggleExpanded: (eventId: string) => void
}) {
  const t = useTranslations("agentTrace")

  return (
    <section
      className="min-h-0 overflow-y-auto px-[22px] py-2.5 [scrollbar-gutter:stable]"
      aria-label={t("timeline.label")}
    >
      <div className="mb-2 flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
        <span className="font-medium text-foreground/72">
          {t("timeline.title")}
        </span>
        <span>{t("timeline.events", { count: view.eventCount })}</span>
      </div>

      {view.preambleEvents.length > 0 ? (
        <section
          className="relative mb-3 min-w-0 pl-[76px]"
          aria-label={t("session")}
        >
          <div className="absolute inset-y-0 left-[57px] w-px bg-border/80" aria-hidden="true" />
          <div className="absolute left-0 top-1 w-[52px] text-right text-[9px] font-semibold leading-4 text-foreground/68">
            {t("session")}
          </div>
          <TurnEvents
            events={view.preambleEvents}
            selectedEventId={selectedEventId}
            expandedEventIds={expandedEventIds}
            onSelectEvent={onSelectEvent}
            onToggleExpanded={onToggleExpanded}
          />
        </section>
      ) : null}

      {view.turns.map((turn) => (
        <section
          key={turn.id}
          className="relative min-w-0 pl-[76px] [content-visibility:auto] [contain-intrinsic-size:auto_320px] [&+&]:mt-3"
          aria-label={t("turn", { index: turn.index })}
        >
          <div className="absolute inset-y-0 left-[57px] w-px bg-border/80" aria-hidden="true" />
          <div className="absolute left-0 top-1 w-[52px] text-right text-[9px] leading-4 text-muted-foreground">
            <strong className="block font-semibold text-foreground/68">
              {t("turn", { index: turn.index })}
            </strong>
            <span>{t("timeline.events", { count: turn.events.length })}</span>
          </div>

          <TurnEvents
            events={turn.events}
            selectedEventId={selectedEventId}
            expandedEventIds={expandedEventIds}
            onSelectEvent={onSelectEvent}
            onToggleExpanded={onToggleExpanded}
          />
        </section>
      ))}

      {view.turns.length === 0 && view.preambleEvents.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          {t("empty")}
        </p>
      ) : null}
    </section>
  )
}

function TurnEvents({
  events,
  selectedEventId,
  expandedEventIds,
  onSelectEvent,
  onToggleExpanded,
}: {
  events: AgentTraceEvent[]
  selectedEventId: string | null
  expandedEventIds: ReadonlySet<string>
  onSelectEvent: (event: AgentTraceEvent) => void
  onToggleExpanded: (eventId: string) => void
}) {
  let previousPhase: AgentTracePhase | null = null
  return events.map((event) => {
    const showPhase = event.phase !== previousPhase
    previousPhase = event.phase
    return (
      <div key={event.id}>
        {showPhase ? <TracePhase phase={event.phase} /> : null}
        <TraceEventRow
          event={event}
          selected={event.id === selectedEventId}
          expanded={expandedEventIds.has(event.id)}
          onSelect={() => onSelectEvent(event)}
          onToggleExpanded={() => onToggleExpanded(event.id)}
        />
      </div>
    )
  })
}

function TracePhase({ phase }: { phase: AgentTracePhase }) {
  const t = useTranslations("agentTrace")
  return (
    <div className="mb-1 mt-2 text-[9px] font-medium uppercase tracking-[0.12em] text-muted-foreground/65 first:mt-0">
      {t(`phase.${phase}`)}
    </div>
  )
}

function TraceEventRow({
  event,
  selected,
  expanded,
  onSelect,
  onToggleExpanded,
}: {
  event: AgentTraceEvent
  selected: boolean
  expanded: boolean
  onSelect: () => void
  onToggleExpanded: () => void
}) {
  const t = useTranslations("agentTrace")
  const selectable =
    event.hasDetail || event.category === "assistant" || event.category === "tool"
  const expandable = event.summary.includes("\n") || event.summary.length > 120

  return (
    <article
      className={cn(
        "group/event relative mb-[5px] grid min-h-[41px] min-w-0 grid-cols-[96px_minmax(0,1fr)_auto] items-start gap-2 rounded-[11px] border border-border/75 bg-card px-[7px] py-2 transition-[transform,border-color,box-shadow] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] hover:translate-x-[3px] motion-reduce:transition-none",
        selected &&
          "border-[color-mix(in_srgb,var(--brand-accent)_35%,var(--border))] shadow-[inset_2px_0_0_var(--brand-accent),0_8px_22px_rgba(23,27,34,0.05)] dark:shadow-[inset_2px_0_0_var(--brand-accent),0_8px_22px_rgba(0,0,0,0.13)]",
      )}
      data-category={event.category}
      data-testid="agent-trace-event"
    >
      {selectable ? (
        <button
          type="button"
          className="absolute inset-0 z-0 rounded-[11px] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/55"
          aria-label={t(
            event.hasDetail ? "event.openDetail" : "event.select",
            { title: event.title },
          )}
          onClick={onSelect}
        />
      ) : null}
      <span
        className={cn(
          "pointer-events-none relative z-[1] mt-0.5 w-fit rounded-[5px] px-1.5 py-0.5 font-mono text-[8px] font-semibold tracking-[0.08em]",
          TRACE_CATEGORY_STYLES[event.category].badge,
        )}
        translate="no"
      >
        {t(`category.${event.category}`)}
      </span>
      <div className="pointer-events-none relative z-[1] min-w-0">
        <div
          className={cn(
            "truncate font-mono text-[12px] leading-5 text-foreground/78",
            event.category !== "tool" && "font-sans text-[13px]",
          )}
          title={event.firstLine}
          translate="no"
        >
          {event.firstLine}
        </div>
        {expanded ? (
          <pre
            className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words border-l border-border/70 pl-3 font-mono text-[11px] leading-5 text-foreground/68"
            translate="no"
          >
            {event.summary}
          </pre>
        ) : null}
      </div>
      <div className="pointer-events-none relative z-[2] flex items-center gap-1">
        <TraceStatus status={event.status} />
        {expandable ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="pointer-events-auto size-7 text-muted-foreground/60 hover:bg-muted/55 hover:text-foreground"
            aria-label={t(expanded ? "event.collapse" : "event.expand", {
              title: event.title,
            })}
            aria-expanded={expanded}
            onClick={(clickEvent) => {
              clickEvent.stopPropagation()
              onToggleExpanded()
            }}
          >
            {expanded ? (
              <ChevronDown aria-hidden="true" />
            ) : (
              <ChevronRight aria-hidden="true" />
            )}
          </Button>
        ) : null}
      </div>
      <span
        className={cn(
          "absolute -left-[22px] top-[17px] size-[7px] rounded-full border-2 border-background",
          TRACE_CATEGORY_STYLES[event.category].dot,
        )}
        aria-hidden="true"
      />
    </article>
  )
}

function TraceStatus({ status }: { status: string | null }) {
  const t = useTranslations("agentTrace")
  if (!status) return null
  const normalized = status.toLowerCase()
  const complete = ["completed", "ready", "received", "success"].includes(
    normalized,
  )
  const running = ["running", "pending", "queued"].includes(normalized)
  const failed = ["failed", "error", "cancelled", "blocked"].includes(
    normalized,
  )
  const Icon = complete ? Check : running ? Loader2 : failed ? Circle : CircleDashed
  const localizedStatus = isKnownTraceStatus(normalized)
    ? t(`status.${TRACE_STATUS_KEYS[normalized]}`)
    : status

  return (
    <span
      className={cn(
        "flex max-w-24 items-center gap-1 truncate text-[9px] text-muted-foreground",
        failed && "text-error-foreground",
      )}
      title={status}
      translate="no"
    >
      <Icon
        aria-hidden="true"
        className={cn("size-3 shrink-0", running && "animate-spin motion-reduce:animate-none")}
      />
      <span className="hidden truncate xl:inline">{localizedStatus}</span>
    </span>
  )
}

function TraceInspector({
  event,
  detail,
  loading,
  error,
  onClose,
  onRetry,
}: {
  event: AgentTraceEvent
  detail: AgentTraceEventDetail | null
  loading: boolean
  error: boolean
  onClose: () => void
  onRetry: () => void
}) {
  const t = useTranslations("agentTrace")
  const [activeTab, setActiveTab] = useState<InspectorTab>("summary")

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border/70 px-3">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={cn(
              "rounded-[5px] px-1.5 py-0.5 font-mono text-[8px] font-semibold tracking-[0.08em]",
              TRACE_CATEGORY_STYLES[event.category].badge,
            )}
            translate="no"
          >
            {t(`category.${event.category}`)}
          </span>
          <code
            className="truncate text-[10px] text-muted-foreground"
            translate="no"
          >
            {event.id}
          </code>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
          aria-label={t("inspector.close")}
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </Button>
      </header>

      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as InspectorTab)}
        className="min-h-0 flex-1 gap-0"
      >
        <div className="shrink-0 overflow-x-auto border-b border-border/70 px-2 [scrollbar-width:none]">
          <TabsList className="h-9 min-w-max gap-0 rounded-none bg-transparent p-0">
            {INSPECTOR_TABS.map((tab) => (
              <TabsTrigger
                key={tab}
                value={tab}
                className="h-9 rounded-none border-0 border-b-2 border-transparent px-2 text-[10px] font-medium text-muted-foreground shadow-none data-[state=active]:border-foreground/65 data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
              >
                {t(`inspector.tabs.${tab}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <div className="min-h-0 flex-1 overflow-auto p-3.5">
          {loading ? (
            <div className="flex h-24 items-center justify-center" role="status">
              <Loader2 className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden="true" />
              <span className="sr-only">{t("loading")}</span>
            </div>
          ) : error ? (
            <div className="grid justify-items-start gap-2">
              <p role="alert" className="text-xs text-error-foreground">
                {t("detailError")}
              </p>
              <Button type="button" variant="outline" size="sm" onClick={onRetry}>
                {t("retry")}
              </Button>
            </div>
          ) : detail ? (
            <>
              <TabsContent value="summary" className="m-0">
                <SummaryPane value={detail.summary} />
              </TabsContent>
              <TabsContent value="payload" className="m-0">
                <RawPane value={detail.payload} />
              </TabsContent>
              <TabsContent value="result" className="m-0">
                <RawPane value={detail.result} />
              </TabsContent>
              <TabsContent value="schema" className="m-0">
                <RawPane value={detail.schema} />
              </TabsContent>
              <TabsContent value="timing" className="m-0">
                <TimingPane timing={detail.timing} />
              </TabsContent>
            </>
          ) : null}
        </div>
      </Tabs>
    </div>
  )
}

function SummaryPane({
  value,
}: {
  value: { [key: string]: TraceJsonValue }
}) {
  return (
    <dl className="grid grid-cols-[92px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[11px] leading-5">
      {Object.entries(value).map(([key, item]) => (
        <div key={key} className="contents">
          <dt className="truncate text-muted-foreground">{humanizeKey(key)}</dt>
          <dd className="min-w-0 break-words font-mono text-foreground/78">
            {compactJson(item)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function RawPane({ value }: { value: TraceJsonValue }) {
  return (
    <pre
      className="min-w-0 whitespace-pre-wrap break-words rounded-[8px] bg-muted/45 p-3 font-mono text-[11px] leading-5 text-foreground/78 ring-1 ring-border/50"
      translate="no"
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function TimingPane({
  timing,
}: {
  timing: AgentTraceEventDetail["timing"]
}) {
  const t = useTranslations("agentTrace")
  if (!timing) {
    return <p className="text-xs text-muted-foreground">{t("unavailable")}</p>
  }
  const rows = [
    [t("inspector.timing.started"), timing.startedAt],
    [t("inspector.timing.requestPrepared"), timing.requestPreparedAt],
    [t("inspector.timing.firstByte"), timing.firstByteAt],
    [t("inspector.timing.completed"), timing.completedAt],
    [
      t("inspector.timing.duration"),
      timing.durationMs === null
        ? null
        : t("units.durationMs", { value: timing.durationMs }),
    ],
  ]
  return (
    <dl className="grid grid-cols-[82px_minmax(0,1fr)] gap-x-3 gap-y-2 text-[11px] leading-5">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-words font-mono text-foreground/78">
            {value ?? t("unavailable")}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function AgentTracePanel({
  sessionId,
  active,
}: {
  sessionId: string
  active: boolean
}) {
  const t = useTranslations("agentTrace")
  const { view, isLoading, error, retry, loadDetail } = useAgentTrace(
    sessionId,
    active,
  )

  if (isLoading && !view) {
    return (
      <div
        className="grid h-full min-h-0 place-items-center"
        role="status"
        aria-live="polite"
        aria-busy="true"
      >
        <Loader2 className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden="true" />
        <span className="sr-only">{t("loading")}</span>
      </div>
    )
  }
  if (error && !view) {
    return (
      <div className="grid h-full min-h-0 place-items-center px-6 text-center">
        <div className="grid gap-3">
          <p className="text-sm text-muted-foreground">{t("loadError")}</p>
          <Button type="button" variant="outline" size="sm" onClick={retry}>
            {t("retry")}
          </Button>
        </div>
      </div>
    )
  }
  return view ? <AgentTraceView view={view} onLoadDetail={loadDetail} /> : null
}

function snapshotAtSequence(
  snapshots: AgentTraceContextSnapshot[],
  sequence: number,
) {
  return [...snapshots]
    .reverse()
    .find((snapshot) => snapshot.sequence <= sequence) ?? snapshots[0] ?? null
}

function snapshotWeight(snapshot: AgentTraceContextSnapshot) {
  if (snapshot.inputTokens !== null) return Math.max(snapshot.inputTokens, 1)
  return Math.max(
    snapshot.composition.reduce((sum, item) => sum + item.characters, 0),
    1,
  )
}

function formatCompactNumber(
  value: number,
  formatThousands: (formatted: string) => string,
) {
  if (value < 1000) return String(value)
  return formatThousands(
    new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(
      value / 1000,
    ),
  )
}

function humanizeKey(key: string) {
  return key.replaceAll("_", " ")
}

function compactJson(value: TraceJsonValue) {
  if (typeof value === "string") return value
  return JSON.stringify(value)
}

function isKnownTraceStatus(
  status: string,
): status is keyof typeof TRACE_STATUS_KEYS {
  return status in TRACE_STATUS_KEYS
}
