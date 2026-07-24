"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import { ArrowRight, Gauge } from "@/lib/icons"
import { CardRoot } from "@/components/bioinfoflow/card/card-base"
import { Button } from "@/components/ui/button"
import type {
  ResourceStreamConnectionState,
  ResourceStreamFrame,
  SchedulerStatus,
} from "@/lib/types"
import { useResourceStream } from "@/hooks/use-resource-stream"
import { PressureHero } from "./pressure-hero"
import { ActiveRunsList } from "./active-runs-list"
import { AdvancedDrawer } from "./advanced-drawer"
import { computePressure } from "./scoring"

type ResourceMonitorProps = {
  initialFrame?: ResourceStreamFrame | null
  schedulerStatus?: SchedulerStatus | null
}

function frameFromStatus(status: SchedulerStatus): ResourceStreamFrame {
  return {
    mode: status.mode,
    effective_mode: status.effective_mode,
    scheduler_available: status.scheduler_available,
    resources: {
      enabled: status.resource_monitoring_enabled,
      sampled_at: null,
      cpu: { total: null, available: null },
      memory: { total_gb: null, available_gb: null },
      disk: { total_gb: null, available_gb: null },
      gpu: { count: 0, memory_gb: 0 },
    },
    active_runs: status.active_runs,
    queue_depth: status.queue_depth,
    states: status.states,
    total_slots: status.total_slots,
    used_slots: status.used_slots,
    available_slots: status.available_slots,
  }
}

export function ResourceMonitor({
  initialFrame = null,
  schedulerStatus = null,
}: ResourceMonitorProps) {
  const t = useTranslations("scheduler")
  const { connectionState, frame, samples } = useResourceStream({
    maxSamples: 60,
  })
  const [highlightedRunId, setHighlightedRunId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useDrawerToggleKey(() => setDrawerOpen((p) => !p))

  const latestFrame =
    frame ?? initialFrame ?? (schedulerStatus ? frameFromStatus(schedulerStatus) : null)

  const current = samples.at(-1) ?? null
  const cpuPercent = current?.cpu ?? null
  const memUsedGb = current?.memUsedGb ?? null
  const memTotalGb = current?.memTotalGb ?? 0
  const load =
    current?.cpuCores != null && current.cpuAvailable != null
      ? Math.max(0, current.cpuCores - current.cpuAvailable)
      : null
  const queueDepth = latestFrame?.queue_depth ?? 0

  const pressure = computePressure({
    cpu: cpuPercent ?? 0,
    memUsedGb: memUsedGb ?? 0,
    memTotalGb: memTotalGb || 1,
    load: load ?? 0,
    cores: current?.cpuCores ?? 0,
    queue: queueDepth,
  })

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

  const capacityState =
    latestFrame?.scheduler_available === false || latestFrame?.resources.enabled === false
      ? "unavailable"
      : samples.length === 0
        ? "pending"
        : "ready"
  const activeRunCount = latestFrame?.active_runs.length ?? 0

  return (
    <>
      <CardRoot
        variant="workbench"
        data-layout="flat-sections"
        className="grid overflow-hidden lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]"
      >
        <section className="min-w-0 p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <h2 className="text-sm font-medium text-foreground">{t("resources")}</h2>
              <LiveStatus connectionState={connectionState} label={trustText} />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setDrawerOpen(true)}
              className="shrink-0 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              <Gauge className="h-3.5 w-3.5" aria-hidden="true" />
              {t("advanced.button")}
              <kbd className="ml-0.5 rounded border border-border bg-muted px-1.5 py-[1px] font-mono text-[10px] text-muted-foreground">
                t
              </kbd>
            </Button>
          </div>
          <div className="mt-5 grid gap-4">
            {capacityState === "ready" ? (
              <PressureHero
                pressure={pressure}
                factors={{ cpu: cpuPercent, memUsedGb, load, queueDepth }}
              />
            ) : (
              <CapacityNotice state={capacityState} />
            )}
            <div className="grid grid-cols-2 gap-2">
              <SnapshotMetric label={t("charts.cpuUtil")} value={cpuCur} />
              <SnapshotMetric label={t("charts.memory")} value={memCur} />
              <SnapshotMetric label={t("charts.diskIo")} value={diskCur} />
              <SnapshotMetric label={t("charts.gpuFree")} value={gpuCur} />
            </div>
          </div>
        </section>

        <section className="min-w-0 border-t border-border/70 p-5 lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <h2 className="text-sm font-medium text-foreground">
                {t("activeRuns.title")}
              </h2>
              {activeRunCount > 0 ? (
                <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                  {t("activeRuns.count", { count: activeRunCount })}
                </span>
              ) : null}
            </div>
            <Button variant="ghost" size="sm" asChild>
              <Link
                href="/runs?scope=all"
                className="shrink-0 gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                {t("activeRuns.viewAll")}
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            </Button>
          </div>
          <div className="mt-5">
            <ActiveRunsList
              runs={latestFrame?.active_runs ?? []}
              cpuPercent={cpuPercent}
              highlightedRunId={highlightedRunId}
              queueDepth={queueDepth}
              connectionState={connectionState}
              onToggleHighlight={(id) =>
                setHighlightedRunId((prev) => (prev === id ? null : id))
              }
            />
          </div>
        </section>
      </CardRoot>

      <AdvancedDrawer open={drawerOpen} onOpenChange={setDrawerOpen} />
    </>
  )
}

function CapacityNotice({ state }: { state: "pending" | "unavailable" }) {
  const t = useTranslations("scheduler")
  const unavailable = state === "unavailable"

  return (
    <div
      className={`rounded-lg border px-4 py-5 ${
        unavailable
          ? "border-warning-border bg-warning-muted/50"
          : "border-border/70 bg-muted/20"
      }`}
    >
      <div
        className={`mb-4 h-1.5 w-16 rounded-full ${
          unavailable ? "bg-warning" : "bg-muted-foreground/40"
        }`}
      />
      <p className="text-sm font-medium text-foreground">
        {unavailable ? t("resourcesUnavailable") : t("resourceSnapshotPending")}
      </p>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        {unavailable
          ? t("resourcesUnavailableBody")
          : t("resourceSnapshotPendingBody")}
      </p>
    </div>
  )
}

function SnapshotMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2">
      <p className="truncate text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 truncate font-mono text-sm font-medium text-foreground">
        {value}
      </p>
    </div>
  )
}

function LiveStatus({
  connectionState,
  label,
}: {
  connectionState: ResourceStreamConnectionState
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-2 text-[11px] text-muted-foreground">
      <LiveDot connected={connectionState === "connected"} />
      {label}
    </span>
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
