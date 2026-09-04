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
  AgentTraceViewModel,
  TraceJsonValue,
} from "@/lib/agent/trace-model/types"
import {
  createContextWindowPresentation,
  findContextSnapshotForSequence,
} from "@/lib/agent/trace-model/context-window"
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
    const preference = ["system", "user", "context"].includes(event.category)
      ? "containing"
      : "preceding"
    const request = findContextSnapshotForSequence(
      view.contextFlow,
      event.sequence,
      preference,
    )
    if (request) setPlayheadSequence(request.sequence)
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
      <TraceContextOverview
        snapshots={view.contextFlow}
        turns={view.turns.map((turn) => ({
          id: turn.id,
          index: turn.index,
          modelLabel: turn.model?.displayName ?? view.session.model.displayName,
        }))}
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
            className="flex min-h-0 w-[400px] flex-col border-l border-border/70 bg-background"
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
                {selectedEvent
                  ? localizedTraceEventTitle(selectedEvent, t)
                  : t("inspector.label")}
              </SheetDescription>
            </SheetHeader>
            {inspector}
          </SheetContent>
        </Sheet>
      ) : null}
    </section>
  )
}

function TraceContextOverview({
  snapshots,
  turns,
  playheadSequence,
  onSelectSnapshot,
}: {
  snapshots: AgentTraceContextSnapshot[]
  turns: Array<{ id: string; index: number; modelLabel: string }>
  playheadSequence: number
  onSelectSnapshot: (sequence: number) => void
}) {
  const t = useTranslations("agentTrace")
  const orderedSnapshots = snapshots.toSorted(
    (left, right) => left.sequence - right.sequence,
  )
  const snapshot = findContextSnapshotForSequence(
    orderedSnapshots,
    playheadSequence,
    "preceding",
  )
  const presentation = snapshot
    ? createContextWindowPresentation(snapshot)
    : null
  const requestGroups = turns
    .map((turn) => ({
      ...turn,
      requests: orderedSnapshots.filter((item) => item.turnId === turn.id),
    }))
    .filter((turn) => turn.requests.length > 0)
  const selectedGroup = snapshot
    ? requestGroups.find((turn) => turn.id === snapshot.turnId)
    : null
  const selectedRequestIndex =
    snapshot && selectedGroup
      ? selectedGroup.requests.findIndex((item) => item.id === snapshot.id) + 1
      : null
  const compactNumber = (value: number) =>
    formatCompactNumber(value, (formatted) =>
      t("units.thousand", { value: formatted }),
    )
  const usedWidth = presentation?.usedPercent ?? 0
  const knownCapacity = presentation?.usedPercent !== null && presentation !== null

  return (
    <section
      className="shrink-0 border-b border-border/70 bg-background px-[22px] pb-3 pt-3"
      aria-label={t("contextWindow.label")}
      role="region"
    >
      <div className="flex min-w-0 items-start justify-between gap-5">
        <div className="min-w-0">
          <h2 className="text-[11px] font-semibold tracking-[-0.01em] text-foreground/78">
            {t("contextWindow.title")}
          </h2>
          {selectedGroup && selectedRequestIndex ? (
            <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
              {t("requestNavigator.selection", {
                turn: selectedGroup.index,
                index: selectedRequestIndex,
                model: selectedGroup.modelLabel,
              })}
            </p>
          ) : null}
        </div>

        <div className="min-w-0 text-right tabular-nums" translate="no">
          {presentation?.usedTokens !== null &&
          presentation?.capacityTokens !== null ? (
            <div className="text-[12px] font-semibold text-foreground/82">
              {t("contextWindow.usedOfLimit", {
                used: compactNumber(presentation.usedTokens),
                limit: compactNumber(presentation.capacityTokens),
              })}
            </div>
          ) : presentation?.usedTokens !== null && presentation ? (
            <div className="text-[12px] font-semibold text-foreground/82">
              {t("contextWindow.used", {
                count: compactNumber(presentation.usedTokens),
              })}
            </div>
          ) : null}
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            {presentation?.usedPercent !== null && presentation ? (
              t("contextWindow.percent", { value: presentation.usedPercent })
            ) : (
              t("contextWindow.limitUnavailable")
            )}
          </div>
        </div>
      </div>

      <div
        data-testid="context-window-track"
        data-state={knownCapacity ? "available" : "unavailable"}
        className="relative mt-2.5 h-[22px] overflow-hidden rounded-[7px] border border-border/75 bg-muted/60 p-[3px] shadow-[inset_0_1px_1px_rgba(0,0,0,0.04)]"
        role={knownCapacity ? "progressbar" : undefined}
        aria-valuemin={knownCapacity ? 0 : undefined}
        aria-valuemax={knownCapacity ? 100 : undefined}
        aria-valuenow={knownCapacity ? usedWidth : undefined}
      >
        {knownCapacity && presentation ? (
          <div
            data-testid="context-window-used"
            className="flex h-full min-w-0 overflow-hidden rounded-[4px] transition-[width] duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:transition-none"
            style={{ width: `${usedWidth}%` }}
          >
            {presentation.composition.map((segment, index) => (
              <span
                key={`${segment.category}:${index}`}
                className={cn(
                  "h-full min-w-px border-r border-background/35 last:border-r-0",
                  TRACE_CATEGORY_STYLES[segment.category].context,
                )}
                style={{ flexGrow: segment.percent }}
                aria-hidden="true"
              />
            ))}
          </div>
        ) : (
          <div className="h-full rounded-[4px] border border-dashed border-border/70 bg-background/25" />
        )}
      </div>

      <div className="mt-2 flex min-w-0 items-center justify-between gap-4">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-muted-foreground">
          {presentation?.composition.map((segment) => (
            <span key={segment.category} className="inline-flex items-center gap-1.5">
              <span
                className={cn(
                  "size-1.5 rounded-[2px]",
                  TRACE_CATEGORY_STYLES[segment.category].context,
                )}
                aria-hidden="true"
              />
              {t(`category.${segment.category}`)}
            </span>
          ))}
          {presentation?.compositionEstimated ? (
            <span className="text-muted-foreground/65">
              {t("contextWindow.compositionEstimated")}
            </span>
          ) : null}
        </div>

        <div
          className="flex shrink-0 items-center gap-3 whitespace-nowrap text-[9px] text-muted-foreground tabular-nums"
          translate="no"
        >
          {presentation?.cachedInputTokens !== null && presentation ? (
            <span>
              {t("contextWindow.cached", {
                count: compactNumber(presentation.cachedInputTokens),
              })}
            </span>
          ) : null}
          {presentation?.outputTokens !== null && presentation ? (
            <span>
              {t("contextWindow.output", {
                count: compactNumber(presentation.outputTokens),
              })}
            </span>
          ) : null}
          {presentation?.reasoningTokens !== null && presentation ? (
            <span>
              {t("contextWindow.reasoning", {
                count: compactNumber(presentation.reasoningTokens),
              })}
            </span>
          ) : null}
        </div>
      </div>

      <nav
        className="mt-2.5 border-t border-border/60 pt-2"
        aria-label={t("requestNavigator.label")}
      >
        <div className="mb-1.5 flex items-center justify-between gap-3 text-[9px] text-muted-foreground">
          <span className="font-medium text-foreground/68">
            {t("requestNavigator.title")}
          </span>
          <span>{t("requestNavigator.requests", { count: orderedSnapshots.length })}</span>
        </div>
        <div className="flex min-w-0 gap-4 overflow-x-auto pb-0.5 [scrollbar-width:none]">
          {requestGroups.map((turn) => (
            <div key={turn.id} className="shrink-0">
              <div className="mb-1 text-[8px] font-semibold text-muted-foreground/70">
                {t("turn", { index: turn.index })}
              </div>
              <div className="relative flex items-center gap-1.5 before:absolute before:inset-x-2 before:top-1/2 before:h-px before:bg-border/80">
                {turn.requests.map((request, index) => {
                  const selected = request.id === snapshot?.id
                  return (
                    <button
                      key={request.id}
                      type="button"
                      className={cn(
                        "relative z-[1] grid size-5 place-items-center rounded-[5px] border border-border/80 bg-background font-mono text-[8px] font-semibold tabular-nums text-muted-foreground outline-none transition-[background-color,border-color,color,transform] duration-150 hover:-translate-y-px hover:border-foreground/25 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/55 motion-reduce:transition-none",
                        selected &&
                          "border-[var(--brand-accent)] bg-[var(--brand-accent)] text-[var(--brand-accent-foreground)]",
                        request.compacted && !selected && "opacity-45",
                      )}
                      aria-label={t("requestNavigator.request", {
                        turn: turn.index,
                        index: index + 1,
                      })}
                      aria-current={selected ? "true" : undefined}
                      onClick={() => onSelectSnapshot(request.sequence)}
                    >
                      {index + 1}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </nav>
    </section>
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
  return events.map((event) => (
    <TraceEventRow
      key={event.id}
      event={event}
      selected={event.id === selectedEventId}
      expanded={expandedEventIds.has(event.id)}
      onSelect={() => onSelectEvent(event)}
      onToggleExpanded={() => onToggleExpanded(event.id)}
    />
  ))
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
  const eventTitle = localizedTraceEventTitle(event, t)
  const selectable =
    event.hasDetail || event.category === "assistant" || event.category === "tool"
  const expandable = event.summary.includes("\n") || event.summary.length > 120
  const showStatus = shouldShowTraceStatus(event)

  return (
    <article
      className={cn(
        "group/event relative grid min-h-[42px] min-w-0 grid-cols-[78px_minmax(0,1fr)_auto] items-start gap-3 border-b border-border/60 px-2 py-2 transition-[background-color] duration-150 hover:bg-muted/30 motion-reduce:transition-none",
        selected &&
          "bg-[var(--brand-accent-muted)]/45 before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-[var(--brand-accent)]",
      )}
      data-category={event.category}
      data-testid="agent-trace-event"
    >
      {selectable ? (
        <button
          type="button"
          className="absolute inset-0 z-0 rounded-[6px] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/55"
          aria-label={t(
            event.hasDetail ? "event.openDetail" : "event.select",
            { title: eventTitle },
          )}
          onClick={onSelect}
        />
      ) : null}
      <span
        className={cn(
          "pointer-events-none relative z-[1] mt-0.5 inline-flex w-fit items-center gap-1.5 font-mono text-[8px] font-semibold tracking-[0.06em] text-muted-foreground",
        )}
        translate="no"
      >
        <span
          className={cn(
            "size-1.5 rounded-[2px]",
            TRACE_CATEGORY_STYLES[event.category].dot,
          )}
          aria-hidden="true"
        />
        {t(`category.${event.category}`)}
      </span>
      <div className="pointer-events-none relative z-[1] min-w-0">
        <div
          className={cn(
            "max-w-[90ch] truncate font-mono text-[12px] leading-5 text-foreground/78",
            event.category !== "tool" && "font-sans text-[13px]",
          )}
          title={event.firstLine}
          translate="no"
        >
          {event.firstLine}
        </div>
        {expanded ? (
          <pre
            className="mt-1.5 max-h-56 max-w-[96ch] overflow-auto whitespace-pre-wrap break-words pl-0 font-mono text-[11px] leading-5 text-foreground/68"
            translate="no"
          >
            {event.summary}
          </pre>
        ) : null}
      </div>
      <div className="pointer-events-none relative z-[2] flex items-center gap-1">
        {showStatus ? <TraceStatus status={event.status} /> : null}
        {expandable ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="pointer-events-auto size-7 text-muted-foreground/60 hover:bg-muted/55 hover:text-foreground"
            aria-label={t(expanded ? "event.collapse" : "event.expand", {
              title: eventTitle,
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
    </article>
  )
}

function shouldShowTraceStatus(event: AgentTraceEvent) {
  const statusKind = classifyTraceStatus(event.status)
  const exceptional = statusKind === "running" || statusKind === "failed"
  return exceptional || event.category === "tool" || event.category === "context"
}

function TraceStatus({
  status,
  showLabel = false,
}: {
  status: string | null
  showLabel?: boolean
}) {
  const t = useTranslations("agentTrace")
  if (!status) return null
  const normalized = status.toLowerCase()
  const statusKind = classifyTraceStatus(normalized)
  const complete = statusKind === "complete"
  const running = statusKind === "running"
  const failed = statusKind === "failed"
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
      <span className={cn("truncate", !showLabel && "hidden xl:inline")}>
        {localizedStatus}
      </span>
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
  const eventTitle = localizedTraceEventTitle(event, t)
  const [activeTab, setActiveTab] = useState<InspectorTab>("summary")
  const failed = isFailedStatus(event.status)
  const diagnostic =
    failed && detail
      ? findDiagnosticText(detail.result) ?? findDiagnosticText(detail.summary)
      : null
  const duration = detail?.timing?.durationMs ?? null

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex min-h-14 shrink-0 items-start justify-between gap-3 border-b border-border/70 px-3.5 py-2.5">
        <div className="min-w-0">
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
            <strong className="truncate text-[12px] font-semibold text-foreground/85">
              {eventTitle}
            </strong>
          </div>
          <code
            className="mt-1 block max-w-[30ch] truncate text-[9px] text-muted-foreground/75"
            title={event.id}
            translate="no"
          >
            {event.id}
          </code>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <TraceStatus status={event.status} showLabel />
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
        </div>
      </header>

      {diagnostic || duration !== null ? (
        <div
          className={cn(
            "shrink-0 border-b border-border/70 px-3.5 py-2.5",
            failed && "border-error-border bg-error-muted/35",
          )}
        >
          {diagnostic ? (
            <p className="text-[11px] leading-5 text-error-foreground">
              {diagnostic}
            </p>
          ) : null}
          {duration !== null ? (
            <div className="mt-1 font-mono text-[9px] tabular-nums text-muted-foreground">
              {t("units.durationMs", { value: duration })}
            </div>
          ) : null}
        </div>
      ) : null}

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

const TRACE_TITLE_PREFIX = "agentTrace.event."

function localizedTraceEventTitle(
  event: AgentTraceEvent,
  translate: (key: string, values?: Record<string, unknown>) => string,
) {
  const code = event.titleCode
  if (!code || !code.startsWith(TRACE_TITLE_PREFIX)) return event.title
  const key = code.slice(TRACE_TITLE_PREFIX.length)
  if (!TRACE_TITLE_KEYS.has(key)) return event.title
  const params = event.titleParams
  return translate(
    `eventTitles.${key}`,
    params && Object.keys(params).length > 0 ? params : undefined,
  )
}

const TRACE_TITLE_KEYS = new Set([
  "system",
  "modelRequest",
  "compaction",
  "contextUpdate",
  "interactionRequest",
  "interactionResponse",
  "notice",
  "plan",
  "context",
  "toolCall",
  "toolResult",
  "reasoning",
  "user",
  "assistant",
  "tool",
])

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
}: {
  sessionId: string
}) {
  const t = useTranslations("agentTrace")
  const { view, isLoading, error, retry, loadDetail } = useAgentTrace(sessionId)

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

function isFailedStatus(status: string | null) {
  return classifyTraceStatus(status) === "failed"
}

function classifyTraceStatus(status: string | null) {
  const normalized = status?.toLowerCase()
  if (["completed", "ready", "received", "success"].includes(normalized ?? "")) {
    return "complete" as const
  }
  if (["running", "pending", "queued"].includes(normalized ?? "")) {
    return "running" as const
  }
  if (["failed", "error", "cancelled", "blocked"].includes(normalized ?? "")) {
    return "failed" as const
  }
  return "other" as const
}

function findDiagnosticText(value: TraceJsonValue): string | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  for (const key of ["error", "message", "reason", "detail", "stderr"]) {
    const candidate = value[key]
    if (typeof candidate === "string" && candidate.trim()) return candidate
  }
  return null
}

function isKnownTraceStatus(
  status: string,
): status is keyof typeof TRACE_STATUS_KEYS {
  return status in TRACE_STATUS_KEYS
}
