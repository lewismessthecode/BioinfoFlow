"use client"

import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import type { RunStatus } from "@/lib/types"
import { Check, Circle, CircleDashed, Loader2, XCircle } from "@/lib/icons"

const STAGES: RunStatus[] = ["pending", "queued", "preparing", "running"]

function isTerminal(status: RunStatus): boolean {
  return status === "completed" || status === "failed" || status === "cancelled"
}

function stageState(stage: RunStatus, status: RunStatus): "done" | "active" | "idle" | "terminal" {
  if (isTerminal(status)) {
    return "terminal"
  }
  const stageIdx = STAGES.indexOf(stage)
  const currentIdx = STAGES.indexOf(status)
  if (currentIdx < 0) return "idle"
  if (stageIdx < currentIdx) return "done"
  if (stageIdx === currentIdx) return "active"
  return "idle"
}

interface RunStagePanelProps {
  status: RunStatus
  currentTask?: string | null
}

export function RunStagePanel({ status, currentTask }: RunStagePanelProps) {
  const t = useTranslations("runs.stage")
  const terminal = isTerminal(status)

  return (
    <div className="rounded-lg border bg-card px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {STAGES.map((stage, index) => {
          const state = stageState(stage, status)
          return (
            <div key={stage} className="flex items-center gap-2">
              <StageDot stage={stage} state={state} />
              <span
                className={cn(
                  "text-xs font-medium",
                  state === "active" && "text-foreground",
                  state === "done" && "text-muted-foreground",
                  state === "idle" && "text-muted-foreground/60",
                  state === "terminal" && "text-muted-foreground/60",
                )}
              >
                {t(stage)}
              </span>
              {index < STAGES.length - 1 ? (
                <div
                  className={cn(
                    "h-px w-6",
                    state === "done" ? "bg-muted-foreground/40" : "bg-border",
                  )}
                />
              ) : null}
            </div>
          )
        })}

        <div className="ml-auto flex items-center gap-2">
          {terminal ? (
            <TerminalDot status={status} />
          ) : currentTask ? (
            <span className="text-xs text-muted-foreground">
              {t("currentTask", { task: currentTask })}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function StageDot({ stage, state }: { stage: RunStatus; state: ReturnType<typeof stageState> }) {
  if (state === "done") {
    return <Check className="size-4 text-muted-foreground" aria-label={`${stage} done`} />
  }
  if (state === "active") {
    return <Loader2 className="size-4 animate-spin text-primary" aria-label={`${stage} active`} />
  }
  if (state === "terminal") {
    return <Circle className="size-3 text-muted-foreground/40" aria-hidden />
  }
  return <CircleDashed className="size-4 text-muted-foreground/60" aria-hidden />
}

function TerminalDot({ status }: { status: RunStatus }) {
  const t = useTranslations("runs.stage")
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-success-foreground">
        <Check className="size-4" />
        {t("completed")}
      </span>
    )
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-error-foreground">
        <XCircle className="size-4" />
        {t("failed")}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <XCircle className="size-4" />
      {t("cancelled")}
    </span>
  )
}
