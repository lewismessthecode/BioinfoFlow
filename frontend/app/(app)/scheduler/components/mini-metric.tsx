"use client"

import type { ReactNode } from "react"
import { useEffect, useRef, useState } from "react"

import { cssColorToRgba } from "./chart-color"

type MiniMetricProps = {
  label: string
  value: string
  icon: ReactNode
  timestamps: number[]
  values: (number | null)[]
  maxScale: number
}

export function MiniMetric({
  label,
  value,
  icon,
  timestamps,
  values,
  maxScale,
}: MiniMetricProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const uplotRef = useRef<any>(null)
  const [ready, setReady] = useState(false)

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

      const cssVar = (name: string) =>
        getComputedStyle(document.documentElement)
          .getPropertyValue(name)
          .trim() || "#888"

      const opts = {
        width: hostRef.current.clientWidth || 200,
        height: 26,
        padding: [3, 2, 1, 2] as [number, number, number, number],
        cursor: { show: false },
        legend: { show: false },
        scales: {
          x: { time: false },
          y: { auto: false, range: [0, maxScale] as [number, number] },
        },
        axes: [{ show: false }, { show: false }],
        series: [
          {},
          {
            stroke: () => cssVar("--muted-foreground"),
            width: 1.3,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            fill: (u: any) => {
              const g = u.ctx.createLinearGradient(0, 0, 0, u.bbox.height)
              const c = cssVar("--muted-foreground")
              g.addColorStop(0, cssColorToRgba(c, 0.13))
              g.addColorStop(1, cssColorToRgba(c, 0))
              return g
            },
            points: { show: false },
          },
        ],
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      uplotRef.current = new (uPlot as any)(opts, [[], []], wrap)
      setReady(true)
    })()

    return () => {
      disposed = true
      uplotRef.current?.destroy?.()
      uplotRef.current = null
      setReady(false)
    }
  }, [maxScale])

  useEffect(() => {
    if (!ready || !uplotRef.current) return
    uplotRef.current.setData([timestamps, values])
  }, [ready, timestamps, values])

  useEffect(() => {
    if (!hostRef.current) return
    const host = hostRef.current
    const observer = new ResizeObserver(() => {
      uplotRef.current?.setSize({ width: host.clientWidth, height: 26 })
    })
    observer.observe(host)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="flex items-center gap-3 rounded-md border border-divider bg-surface-subtle px-3 py-2.5">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
        {icon}
      </span>
      <div className="shrink-0">
        <div className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          {label}
        </div>
        <div className="font-mono text-[14px] font-medium -tracking-[0.01em] text-foreground">
          {value}
        </div>
      </div>
      <div ref={hostRef} className="relative h-[26px] min-w-0 flex-1" />
    </div>
  )
}
