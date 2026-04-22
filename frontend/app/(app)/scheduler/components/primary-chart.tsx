"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import type { SchedulerEvent } from "@/hooks/use-resource-stream"

import { cssColorToRgba } from "./chart-color"

type PrimaryChartProps = {
  /** (ts[], value[]) parallel arrays, already windowed by caller. */
  timestamps: number[]
  values: (number | null)[]
  /** Two numeric thresholds in data units — warn band starts at [0], danger at [1]. */
  thresholds: [number, number]
  maxScale: number
  unit: string
  /** Rolling window in seconds — used only for axis labels (handled by parent). */
  events?: SchedulerEvent[]
  className?: string
}

/**
 * Thin uPlot wrapper that owns three concerns the raw library does not:
 * - Threshold bands painted behind the series (safe / warn / danger)
 * - Small markers for scheduler events pinned to the x-axis
 * - Crosshair tooltip that pulls its colour and text from the live theme
 *
 * Everything reads colours through CSS custom properties (`--success`,
 * `--warning`, `--destructive`, `--chart-neutral`, `--card`, ...) so the
 * component adapts to theme changes without code paths for light/dark.
 */
export function PrimaryChart({
  timestamps,
  values,
  thresholds,
  maxScale,
  unit,
  events = [],
  className,
}: PrimaryChartProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const tooltipRef = useRef<HTMLDivElement | null>(null)
  // The `uPlot` type isn't available until it's dynamically imported.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const uplotRef = useRef<any>(null)
  const eventsRef = useRef<SchedulerEvent[]>(events)
  const [ready, setReady] = useState(false)

  // Keep latest events in a ref so the draw plugin closure reads current data
  // without needing the chart to be rebuilt on every tick.
  useEffect(() => {
    eventsRef.current = events
  }, [events])

  const cssVar = useMemo(
    () => (name: string): string => {
      if (typeof window === "undefined") return ""
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    },
    [],
  )

  // Mount + initialise uPlot once.
  useEffect(() => {
    if (!hostRef.current) return

    let disposed = false

    void (async () => {
      const uPlot = (await import("uplot")).default

      if (disposed || !hostRef.current) return

      const wrap = document.createElement("div")
      wrap.style.position = "absolute"
      wrap.style.inset = "0"
      hostRef.current.appendChild(wrap)
      wrapRef.current = wrap

      const tooltip = document.createElement("div")
      tooltip.className =
        "pointer-events-none absolute top-1 z-10 rounded-md border border-border bg-popover px-2 py-1 font-mono text-[11px] text-foreground shadow-sm opacity-0 transition-opacity"
      tooltip.style.transition = "opacity 120ms"
      hostRef.current.appendChild(tooltip)
      tooltipRef.current = tooltip

      const host = hostRef.current

      const bandsPlugin = {
        hooks: {
          drawClear: [
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (u: any) => {
              if (u.scales.y.min == null) return
              const { ctx, bbox } = u
              const bands = [
                { lo: 0, hi: thresholds[0], key: "--success", alpha: 0.06 },
                { lo: thresholds[0], hi: thresholds[1], key: "--warning", alpha: 0.08 },
                { lo: thresholds[1], hi: maxScale, key: "--destructive", alpha: 0.10 },
              ]
              ctx.save()
              for (const band of bands) {
                const yHi = u.valToPos(band.hi, "y", true)
                const yLo = u.valToPos(band.lo, "y", true)
                ctx.globalAlpha = band.alpha
                ctx.fillStyle = cssVar(band.key) || "#888"
                ctx.fillRect(bbox.left, yHi, bbox.width, yLo - yHi)
              }
              ctx.restore()
            },
          ],
        },
      }

      const markersPlugin = {
        hooks: {
          draw: [
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (u: any) => {
              const { ctx, bbox } = u
              ctx.save()
              for (const ev of eventsRef.current) {
                const x = u.valToPos(ev.t, "x", true)
                if (x < bbox.left || x > bbox.left + bbox.width) continue
                const y = bbox.top + bbox.height - 4
                ctx.fillStyle =
                  ev.kind === "dispatch"
                    ? cssVar("--success") || "#22c55e"
                    : cssVar("--muted-foreground") || "#666"
                ctx.globalAlpha = ev.kind === "dispatch" ? 0.9 : 0.55
                ctx.beginPath()
                ctx.arc(x, y, 2.5, 0, Math.PI * 2)
                ctx.fill()
              }
              ctx.restore()
            },
          ],
        },
      }

      const opts = {
        width: host.clientWidth || 400,
        height: host.clientHeight || 88,
        padding: [6, 4, 2, 4] as [number, number, number, number],
        cursor: {
          show: true,
          x: true,
          y: false,
          drag: { setScale: false },
          points: { show: false },
        },
        legend: { show: false },
        scales: {
          x: { time: false },
          y: { auto: false, range: [0, maxScale] as [number, number] },
        },
        axes: [{ show: false }, { show: false }],
        series: [
          {},
          {
            stroke: () => cssVar("--chart-neutral") || "#404040",
            width: 1.5,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            fill: (u: any) => {
              const g = u.ctx.createLinearGradient(0, 0, 0, u.bbox.height)
              const c = cssVar("--chart-neutral") || "#404040"
              g.addColorStop(0, cssColorToRgba(c, 0.13))
              g.addColorStop(1, cssColorToRgba(c, 0))
              return g
            },
            points: { show: false },
          },
        ],
        plugins: [bandsPlugin, markersPlugin],
        hooks: {
          setCursor: [
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (u: any) => {
              const tt = tooltipRef.current
              if (!tt) return
              const idx = u.cursor.idx
              if (idx == null) {
                tt.style.opacity = "0"
                return
              }
              const x = u.data[0][idx]
              const y = u.data[1][idx]
              if (x == null || y == null) {
                tt.style.opacity = "0"
                return
              }
              const leftPx = u.valToPos(x, "x") + 10
              const hostWidth = u.over.offsetWidth
              tt.style.left =
                Math.min(Math.max(leftPx, 4), hostWidth - 120) + "px"
              const ago = Math.round(Date.now() / 1000 - x)
              tt.textContent = `${y.toFixed(1)}${unit}  ${ago <= 0 ? "now" : `−${ago}s`}`
              tt.style.opacity = "1"
            },
          ],
        },
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      uplotRef.current = new (uPlot as any)(opts, [[], []], wrap)
      setReady(true)
    })()

    return () => {
      disposed = true
      uplotRef.current?.destroy?.()
      uplotRef.current = null
      if (wrapRef.current?.parentElement) {
        wrapRef.current.parentElement.removeChild(wrapRef.current)
      }
      if (tooltipRef.current?.parentElement) {
        tooltipRef.current.parentElement.removeChild(tooltipRef.current)
      }
      setReady(false)
    }
    // Intentionally only re-run on prop changes that require a rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thresholds[0], thresholds[1], maxScale, unit])

  // Feed new data into the existing chart every tick.
  useEffect(() => {
    if (!ready || !uplotRef.current) return
    const cleaned = values.map((v) => (v == null ? null : v))
    uplotRef.current.setData([timestamps, cleaned])
  }, [ready, timestamps, values])

  // Keep uPlot in sync with its container width.
  useEffect(() => {
    if (!hostRef.current) return
    const host = hostRef.current
    const observer = new ResizeObserver(() => {
      if (!uplotRef.current) return
      uplotRef.current.setSize({
        width: host.clientWidth,
        height: host.clientHeight,
      })
    })
    observer.observe(host)
    return () => observer.disconnect()
  }, [])

  return <div ref={hostRef} className={className} style={{ position: "relative" }} />
}
