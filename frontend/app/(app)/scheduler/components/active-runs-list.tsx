"use client"

import { useTranslations } from "next-intl"
import type { ActiveRun } from "@/lib/types"

type ActiveRunsListProps = {
  runs: ActiveRun[]
  /** Current CPU utilisation (0..100) used to size each run's bar. */
  cpuPercent: number | null
  highlightedRunId: string | null
  onToggleHighlight: (runId: string) => void
}

/**
 * Correlates resource load to the runs that are actually causing it.
 *
 * Per-run CPU share is not directly observable from the host (see plan:
 * follow-up PR will plumb cgroups / Docker stats). For v1 we estimate
 * proportionally from scheduler weights, which is the same allocation the
 * admission controller uses — so the bar widths are honest about *expected*
 * load even if they don't exactly match *instantaneous* usage.
 */
export function ActiveRunsList({
  runs,
  cpuPercent,
  highlightedRunId,
  onToggleHighlight,
}: ActiveRunsListProps) {
  const t = useTranslations("scheduler")

  if (runs.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <Label count={0} />
        <div className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-4 text-center text-xs text-muted-foreground">
          {t("activeRuns.empty")}
        </div>
      </div>
    )
  }

  const totalWeight = runs.reduce((acc, r) => acc + (r.weight || 1), 0)

  return (
    <div className="flex flex-col gap-3">
      <Label count={runs.length} />
      <div className="flex flex-col">
        {runs.map((r) => {
          const share = (r.weight || 1) / totalWeight
          const pct = cpuPercent == null ? 0 : Math.max(2, Math.round(share * cpuPercent))
          const active = highlightedRunId === r.run_id

          return (
            <button
              key={r.run_id}
              type="button"
              onClick={() => onToggleHighlight(r.run_id)}
              className={`grid grid-cols-[7px_minmax(0,1.1fr)_minmax(0,1fr)_50px] items-center gap-3 rounded-md border-b border-dashed border-divider px-2 py-2.5 text-left transition-colors last:border-b-0 hover:bg-muted ${
                active ? "bg-success-muted" : ""
              }`}
            >
              <span
                className="h-[7px] w-[7px] rounded-full bg-success ring-[3px] ring-success-muted"
                aria-hidden="true"
              />
              <span className="truncate text-[13px] font-medium text-foreground">
                <span className="mr-2 font-mono text-[11.5px] text-muted-foreground">
                  {r.run_id}
                </span>
                {r.workflow_name ?? t("activeRuns.unknownWorkflow")}
              </span>
              <span className="relative h-1 rounded-sm bg-muted">
                <span
                  className="absolute inset-y-0 left-0 rounded-sm bg-success transition-[width] duration-300"
                  style={{ width: `${Math.round(share * 100)}%` }}
                />
              </span>
              <span className="text-right font-mono text-[12px] text-muted-foreground">
                {pct}%
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function Label({ count }: { count: number }) {
  const t = useTranslations("scheduler")
  return (
    <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
      <span>{t("activeRuns.title")}</span>
      <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-[11px] normal-case tracking-normal text-foreground">
        {t("activeRuns.count", { count })}
      </span>
    </div>
  )
}
