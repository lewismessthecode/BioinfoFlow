"use client"

import { useTranslations } from "next-intl"
import type {
  ActiveRun,
  ResourceStreamConnectionState,
} from "@/lib/types"

type ActiveRunsListProps = {
  runs: ActiveRun[]
  cpuPercent: number | null
  highlightedRunId: string | null
  queueDepth: number
  connectionState: ResourceStreamConnectionState
  onToggleHighlight: (runId: string) => void
}

export function ActiveRunsList({
  runs,
  cpuPercent,
  highlightedRunId,
  queueDepth,
  connectionState,
  onToggleHighlight,
}: ActiveRunsListProps) {
  const t = useTranslations("scheduler")

  if (runs.length === 0) {
    const state =
      connectionState === "disconnected"
        ? "disconnected"
        : queueDepth > 0
          ? "queued"
          : "idle"

    return (
      <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-5 text-center">
        <span className="mx-auto block h-2 w-2 rounded-full bg-muted-foreground/50" />
        <p className="mt-3 text-sm font-medium text-foreground">
          {t(`activeRuns.emptyStates.${state}.title`)}
        </p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
          {t(`activeRuns.emptyStates.${state}.body`)}
        </p>
      </div>
    )
  }

  const totalWeight = runs.reduce((acc, r) => acc + (r.weight || 1), 0)

  return (
    <div className="space-y-2">
      {runs.map((r) => {
        const share = (r.weight || 1) / totalWeight
        const cpuShare = cpuPercent == null ? 0 : Math.round(share * cpuPercent)
        const barPct = Math.max(2, Math.round(share * 100))
        const active = highlightedRunId === r.run_id

        return (
          <button
            key={r.run_id}
            type="button"
            onClick={() => onToggleHighlight(r.run_id)}
            aria-pressed={active}
            className={`grid w-full grid-cols-[8px_minmax(0,1fr)_64px] items-center gap-3 rounded-lg border px-3 py-3 text-left transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
              active
                ? "border-success-border bg-success-muted"
                : "border-border/70 bg-card"
            }`}
          >
            <span
              className="h-2 w-2 rounded-full bg-success ring-[3px] ring-success-muted"
              aria-hidden="true"
            />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-foreground">
                {r.workflow_name ?? t("activeRuns.unknownWorkflow")}
              </span>
              <span className="mt-1 block truncate font-mono text-[11px] text-muted-foreground">
                {r.run_id}
              </span>
              <span className="mt-2 block h-1 rounded-full bg-muted">
                <span
                  className="block h-full rounded-full bg-success transition-[width] duration-300"
                  style={{ width: `${barPct}%` }}
                />
              </span>
            </span>
            <span className="text-right font-mono text-sm text-muted-foreground">
              {cpuShare}%
            </span>
          </button>
        )
      })}
    </div>
  )
}
