"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import { ChevronsRight, Database, MonitorSmartphone } from "lucide-react"
import type { ResourceStreamFrame } from "@/lib/types"
import { useResourceStream } from "@/hooks/use-resource-stream"
import { PrimaryChart } from "./primary-chart"
import { PressureHero } from "./pressure-hero"
import { ActiveRunsList } from "./active-runs-list"
import { MiniMetric } from "./mini-metric"
import { AdvancedDrawer } from "./advanced-drawer"
import { computePressure } from "./scoring"

type ResourceMonitorProps = {
  /** Fallback when the stream has not yet delivered a frame. */
  initialFrame?: ResourceStreamFrame | null
}

/**
 * Orchestrator for the live scheduler resource panel.
 *
 * Data flow: `useResourceStream` owns the EventSource connection and keeps
 * the sliding window of samples; every child is a pure view of that state.
 * `computePressure` is intentionally host-agnostic (see scoring.ts) so the
 * same math could drive a CLI summary or a notification rule later.
 */
export function ResourceMonitor({ initialFrame = null }: ResourceMonitorProps) {
  const t = useTranslations("scheduler")
  const { connectionState, frame, samples, events } = useResourceStream({
    maxSamples: 60,
  })
  const [highlightedRunId, setHighlightedRunId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // Keyboard shortcut for power users: `t` toggles the Advanced drawer.
  // Guarded so text inputs and editors don't swallow it accidentally.
  useDrawerToggleKey(() => setDrawerOpen((p) => !p))

  const latestFrame = frame ?? initialFrame

  const current = samples.at(-1) ?? null
  const cpuPercent = current?.cpu ?? null
  const memUsedGb = current?.memUsedGb ?? null
  const memTotalGb = current?.memTotalGb ?? 0
  const load =
    current?.cpuCores != null && current.cpuAvailable != null
      ? Math.max(0, current.cpuCores - current.cpuAvailable)
      : null
  const queueDepth = latestFrame?.queue_depth ?? 0

  const pressure = useMemo(
    () =>
      computePressure({
        cpu: cpuPercent ?? 0,
        memUsedGb: memUsedGb ?? 0,
        memTotalGb: memTotalGb || 1,
        load: load ?? 0,
        cores: current?.cpuCores ?? 0,
        queue: queueDepth,
      }),
    [cpuPercent, memUsedGb, memTotalGb, load, current?.cpuCores, queueDepth],
  )

  const timestamps = useMemo(() => samples.map((s) => s.t), [samples])
  const cpuValues = useMemo(() => samples.map((s) => s.cpu), [samples])
  const memValues = useMemo(() => samples.map((s) => s.memUsedGb), [samples])
  const diskValues = useMemo(
    () => samples.map((s) => s.diskUsedGb ?? 0),
    [samples],
  )
  const gpuValues = useMemo(
    () => samples.map((s) => Math.max(0, s.gpuCount > 0 ? s.gpuFreeGb : 0)),
    [samples],
  )

  const diskMax =
    samples.at(-1)?.diskTotalGb ?? Math.max(10, Math.max(...diskValues, 0))
  const gpuMax = Math.max(
    1,
    samples.reduce((acc, s) => Math.max(acc, s.gpuFreeGb), 0) || 12,
  )

  const memThresholds: [number, number] =
    memTotalGb > 0
      ? [memTotalGb * 0.6, memTotalGb * 0.85]
      : [19.2, 27.2]
  const memMax = memTotalGb > 0 ? memTotalGb : 32

  const cpuCur = cpuPercent == null ? "—" : `${cpuPercent.toFixed(1)}%`
  const memCur =
    memUsedGb == null || memTotalGb === 0
      ? "—"
      : `${memUsedGb.toFixed(1)} / ${memTotalGb.toFixed(0)} GB`
  const diskCur =
    current?.diskUsedGb == null
      ? "—"
      : `${current.diskUsedGb.toFixed(1)} GB`
  const gpuCur =
    current == null || current.gpuCount === 0
      ? t("resourceUnavailable")
      : `${current.gpuFreeGb.toFixed(1)} GB`

  const trustText =
    connectionState === "connected"
      ? t("trust.streaming")
      : connectionState === "reconnecting"
        ? t("trust.reconnecting")
        : connectionState === "connecting"
          ? t("trust.connecting")
          : t("trust.disconnected")

  return (
    <>
      <div className="rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-divider px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-foreground">
              {t("resources")}
            </span>
            <span className="inline-flex items-center gap-2 text-[11px] text-muted-foreground">
              <LiveDot connected={connectionState === "connected"} />
              {trustText}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[12px] font-medium text-foreground transition-colors hover:bg-muted"
          >
            <ChevronsRight className="h-3.5 w-3.5" aria-hidden="true" />
            {t("advanced.button")}
            <kbd className="ml-1 rounded border border-border bg-muted px-1.5 py-[1px] font-mono text-[10px] text-muted-foreground">
              t
            </kbd>
          </button>
        </div>

        <div className="grid grid-cols-1 gap-px bg-divider lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div className="bg-card p-5">
            <PressureHero
              pressure={pressure}
              factors={{ cpu: cpuPercent, memUsedGb, load, queueDepth }}
            />
          </div>
          <div className="bg-card p-5">
            <ActiveRunsList
              runs={latestFrame?.active_runs ?? []}
              cpuPercent={cpuPercent}
              highlightedRunId={highlightedRunId}
              onToggleHighlight={(id) =>
                setHighlightedRunId((prev) => (prev === id ? null : id))
              }
            />
          </div>

          <div className="bg-card p-5">
            <ChartHeader label={t("charts.cpuUtil")} value={cpuCur} />
            <div className="relative -mx-1 h-[88px]">
              <PrimaryChart
                timestamps={timestamps}
                values={cpuValues}
                thresholds={[60, 85]}
                maxScale={100}
                unit="%"
                events={events}
                className="h-full w-full"
              />
            </div>
            <AxisTicks />
          </div>
          <div className="bg-card p-5">
            <ChartHeader label={t("charts.memory")} value={memCur} />
            <div className="relative -mx-1 h-[88px]">
              <PrimaryChart
                timestamps={timestamps}
                values={memValues}
                thresholds={memThresholds}
                maxScale={memMax}
                unit=" GB"
                events={events}
                className="h-full w-full"
              />
            </div>
            <AxisTicks />
          </div>

          <div className="col-span-full grid grid-cols-1 gap-4 bg-card p-5 md:grid-cols-2">
            <MiniMetric
              label={t("charts.diskIo")}
              value={diskCur}
              icon={<Database className="h-3.5 w-3.5" />}
              timestamps={timestamps}
              values={diskValues}
              maxScale={diskMax}
            />
            <MiniMetric
              label={t("charts.gpuFree")}
              value={gpuCur}
              icon={<MonitorSmartphone className="h-3.5 w-3.5" />}
              timestamps={timestamps}
              values={gpuValues}
              maxScale={gpuMax}
            />
          </div>
        </div>
      </div>

      <div className="mt-3.5 flex flex-wrap items-center justify-between gap-3 px-1 text-[11.5px] text-muted-foreground">
        <div className="flex flex-wrap items-center gap-4">
          <LegendBand tone="success" label={t("legend.safe")} />
          <LegendBand tone="warning" label={t("legend.warn")} />
          <LegendBand tone="destructive" label={t("legend.danger")} />
          <LegendMarker
            tone="success"
            label={t("legend.dispatch")}
          />
          <LegendMarker tone="muted" label={t("legend.complete")} />
        </div>
        <div className="font-mono text-muted-foreground/80">
          {t("legend.window")}
        </div>
      </div>

      <AdvancedDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />
    </>
  )
}

function ChartHeader({ label, value }: { label: string; value: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between">
      <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-[16px] font-medium -tracking-[0.015em] text-foreground">
        {value}
      </span>
    </div>
  )
}

function AxisTicks() {
  const t = useTranslations("scheduler")
  return (
    <div className="mt-2 flex justify-between px-1 font-mono text-[10.5px] text-muted-foreground/70">
      <span>{t("legend.minus60s")}</span>
      <span>{t("legend.minus30s")}</span>
      <span>{t("legend.now")}</span>
    </div>
  )
}

function LiveDot({ connected }: { connected: boolean }) {
  return (
    <span className="relative inline-flex h-1.5 w-1.5">
      <span
        className={`absolute inline-flex h-full w-full rounded-full ${
          connected ? "bg-success" : "bg-muted-foreground"
        }`}
      />
      {connected && (
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60 motion-reduce:animate-none"
          aria-hidden="true"
        />
      )}
    </span>
  )
}

const BAND_TONES = {
  success: "bg-success/35",
  warning: "bg-warning/45",
  destructive: "bg-destructive/50",
} as const
const MARKER_TONES = {
  success: "bg-success",
  muted: "bg-muted-foreground",
} as const

function LegendBand({
  tone,
  label,
}: {
  tone: keyof typeof BAND_TONES
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-1.5 w-3.5 rounded-sm ${BAND_TONES[tone]}`} aria-hidden="true" />
      {label}
    </span>
  )
}

function LegendMarker({
  tone,
  label,
}: {
  tone: keyof typeof MARKER_TONES
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${MARKER_TONES[tone]}`}
        aria-hidden="true"
      />
      {label}
    </span>
  )
}

function useDrawerToggleKey(onToggle: () => void) {
  const handlerRef = useRef(onToggle)
  useEffect(() => {
    handlerRef.current = onToggle
  })
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return
      if (e.key !== "t") return
      const active = document.activeElement
      if (
        active &&
        (active.tagName === "INPUT" ||
          active.tagName === "TEXTAREA" ||
          (active as HTMLElement).isContentEditable)
      ) {
        return
      }
      handlerRef.current()
    }
    window.addEventListener("keydown", listener)
    return () => window.removeEventListener("keydown", listener)
  }, [])
}
