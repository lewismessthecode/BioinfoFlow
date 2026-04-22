"use client"

import { useEffect, useRef, useState } from "react"
import { buildApiUrl } from "@/lib/api"
import type {
  ActiveRun,
  ResourceStreamConnectionState,
  ResourceStreamFrame,
} from "@/lib/types"

/**
 * One "scheduler event" as the chart needs it: a timestamped dispatch or
 * completion for a specific run. Derived locally by diffing the active-run
 * list between consecutive stream frames, so the frontend does not need a
 * second SSE connection just for markers.
 */
export type SchedulerEvent = {
  t: number // unix seconds
  kind: "dispatch" | "complete"
  run_id: string
}

export type ResourceSample = {
  /** Unix seconds of the browser-side arrival. Used as the x-axis of the live chart. */
  t: number
  cpu: number | null // 0..100
  memUsedGb: number | null
  memTotalGb: number | null
  diskUsedGb: number | null
  diskTotalGb: number | null
  gpuFreeGb: number
  gpuCount: number
  cpuCores: number | null
  cpuAvailable: number | null
}

function toSample(frame: ResourceStreamFrame): ResourceSample {
  const r = frame.resources
  const cpuCores = r.cpu.total
  const cpuAvailable = r.cpu.available
  const cpu =
    cpuCores != null && cpuAvailable != null && cpuCores > 0
      ? Math.max(0, Math.min(100, ((cpuCores - cpuAvailable) / cpuCores) * 100))
      : null
  const memUsedGb =
    r.memory.total_gb != null && r.memory.available_gb != null
      ? Math.max(0, r.memory.total_gb - r.memory.available_gb)
      : null
  const diskUsedGb =
    r.disk.total_gb != null && r.disk.available_gb != null
      ? Math.max(0, r.disk.total_gb - r.disk.available_gb)
      : null
  return {
    t: Date.now() / 1000,
    cpu,
    memUsedGb,
    memTotalGb: r.memory.total_gb,
    diskUsedGb,
    diskTotalGb: r.disk.total_gb,
    gpuFreeGb: r.gpu.memory_gb,
    gpuCount: r.gpu.count,
    cpuCores,
    cpuAvailable,
  }
}

function deriveEvents(
  previous: ActiveRun[],
  next: ActiveRun[],
  t: number
): SchedulerEvent[] {
  const prevIds = new Set(previous.map((r) => r.run_id))
  const nextIds = new Set(next.map((r) => r.run_id))
  const events: SchedulerEvent[] = []
  for (const id of nextIds) {
    if (!prevIds.has(id)) events.push({ t, kind: "dispatch", run_id: id })
  }
  for (const id of prevIds) {
    if (!nextIds.has(id)) events.push({ t, kind: "complete", run_id: id })
  }
  return events
}

const INITIAL_BACKOFF = 1000
const MAX_BACKOFF = 30000
const BACKOFF_MULTIPLIER = 2
const EVENT_WINDOW_SECONDS = 90

type UseResourceStreamOptions = {
  enabled?: boolean
  /** Keep at most the last N samples. Matches the chart rolling window. */
  maxSamples?: number
}

export type UseResourceStreamResult = {
  connectionState: ResourceStreamConnectionState
  frame: ResourceStreamFrame | null
  samples: ResourceSample[]
  events: SchedulerEvent[]
}

export function useResourceStream({
  enabled = true,
  maxSamples = 60,
}: UseResourceStreamOptions = {}): UseResourceStreamResult {
  const [connectionState, setConnectionState] =
    useState<ResourceStreamConnectionState>("disconnected")
  const [frame, setFrame] = useState<ResourceStreamFrame | null>(null)
  const [samples, setSamples] = useState<ResourceSample[]>([])
  const [events, setEvents] = useState<SchedulerEvent[]>([])
  const prevActiveRef = useRef<ActiveRun[]>([])

  useEffect(() => {
    if (!enabled) {
      // Initial state is already "disconnected", and the previous effect
      // run's cleanup sets it back when enabled flips true → false.
      return
    }

    let source: EventSource | null = null
    let backoff = INITIAL_BACKOFF
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let disposed = false

    const setup = () => {
      if (disposed) return
      setConnectionState((prev) =>
        prev === "disconnected" ? "connecting" : "reconnecting"
      )
      const url = buildApiUrl("/scheduler/resources/stream")
      source = new EventSource(url)

      source.onopen = () => {
        if (disposed) return
        backoff = INITIAL_BACKOFF
        setConnectionState("connected")
      }

      source.onerror = () => {
        if (disposed) return
        if (source?.readyState === EventSource.CLOSED) {
          setConnectionState("reconnecting")
          source = null
          reconnectTimer = setTimeout(() => {
            backoff = Math.min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            setup()
          }, backoff)
        }
      }

      source.addEventListener("scheduler.resources", (raw) => {
        const msg = raw as MessageEvent
        let parsed: ResourceStreamFrame
        try {
          parsed = JSON.parse(msg.data) as ResourceStreamFrame
        } catch {
          return
        }

        const sample = toSample(parsed)
        const derived = deriveEvents(
          prevActiveRef.current,
          parsed.active_runs,
          sample.t
        )
        prevActiveRef.current = parsed.active_runs

        setFrame(parsed)
        setSamples((prev) => {
          const next = [...prev, sample]
          while (next.length > maxSamples) next.shift()
          return next
        })
        if (derived.length > 0) {
          setEvents((prev) => {
            const cutoff = sample.t - EVENT_WINDOW_SECONDS
            const merged = [...prev, ...derived].filter((e) => e.t >= cutoff)
            return merged
          })
        }
      })
    }

    setup()

    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      source?.close()
      setConnectionState("disconnected")
    }
  }, [enabled, maxSamples])

  return { connectionState, frame, samples, events }
}
