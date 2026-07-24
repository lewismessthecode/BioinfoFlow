"use client"

import { useTranslations } from "next-intl"
import { Clock, Play, WifiOff } from "@/lib/icons"
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
    const state: "disconnected" | "queued" | "idle" =
      connectionState === "disconnected"
        ? "disconnected"
        : queueDepth > 0
          ? "queued"
          : "idle"
    const EmptyIcon =
      state === "disconnected" ? WifiOff : state === "queued" ? Clock : Play

    return (
      <div
        data-testid="active-runs-empty-state"
        className="border-t border-border/70 py-5"
      >
        <div className="flex items-start gap-3">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted/35 text-muted-foreground">
            <EmptyIcon className="size-3.5" aria-hidden="true" />
          </span>
          <div className="min-w-0 pt-0.5">
            <p className="text-sm font-medium text-foreground">
              {t(`activeRuns.emptyStates.${state}.title`)}
            </p>
            <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
              {t(`activeRuns.emptyStates.${state}.body`)}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const totalWeight = runs.reduce((acc, r) => acc + (r.weight || 1), 0)

  return (
    <div className="overflow-hidden rounded-lg border border-border/70">
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
            className={`grid min-h-16 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-b border-border/70 px-4 py-3 text-left transition-[background-color,transform] last:border-b-0 hover:bg-muted/35 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-50 ${
              active
                ? "bg-muted/45"
                : "bg-card"
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
