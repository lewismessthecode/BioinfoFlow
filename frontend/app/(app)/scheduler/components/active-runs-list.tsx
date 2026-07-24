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
        const active = highlightedRunId === r.run_id

        return (
          <button
            key={r.run_id}
            type="button"
            onClick={() => onToggleHighlight(r.run_id)}
            aria-pressed={active}
            className={`grid min-h-16 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-lg border px-4 py-3 text-left transition-[background-color,border-color,transform] hover:bg-muted/50 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 ${
              active
                ? "border-foreground/20 bg-muted/45"
                : "border-border/70 bg-card"
            }`}
          >
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-foreground">
                {r.workflow_name ?? t("activeRuns.unknownWorkflow")}
              </span>
              <span className="mt-1 block truncate font-mono text-[11px] text-muted-foreground">
                {r.run_id}
              </span>
            </span>
            <span className="text-right">
              <span className="block text-[11px] text-muted-foreground">
                {t("activeRuns.cpuShare")}
              </span>
              <span className="mt-1 block font-mono text-sm font-medium tabular-nums text-foreground">
                {cpuShare}%
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
