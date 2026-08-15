"use client"

import { useLocale, useTranslations } from "next-intl"

import { Badge } from "@/components/ui/badge"
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
} from "@/lib/icons"
import {
  dateTimeAttribute,
  formatAgentDuration,
  formatAgentEndTime,
} from "@/lib/agent/date-format"
import type { RunView } from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type TerminalRun = RunView & {
  status: "completed" | "failed" | "cancelled"
}

export function AgentRunOutcome({ run }: { run: TerminalRun }) {
  const locale = useLocale()
  const tRun = useTranslations("agentRun")
  const tTranscript = useTranslations("agentTranscript")
  const endTime = formatAgentEndTime(run.completed_at, locale)
  const duration = formatAgentDuration(
    run.started_at,
    run.completed_at,
    locale,
  )
  const statusLabel = tRun(`status.${run.status}`)
  const Icon =
    run.status === "completed"
      ? CheckCircle2
      : run.status === "failed"
        ? AlertTriangle
        : CircleDashed

  return (
    <section
      aria-label={statusLabel}
      className={cn(
        "grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-2.5 rounded-[10px] border border-border/60 bg-muted/20 px-3 py-2.5 [content-visibility:auto] [contain-intrinsic-size:auto_80px]",
        run.status === "failed" && "border-error-border bg-error-muted/25",
      )}
      data-testid="agent-run-outcome"
    >
      <Icon
        aria-hidden="true"
        className={cn(
          "mt-0.5 size-4 shrink-0 text-muted-foreground",
          run.status === "failed" && "text-error-foreground",
        )}
      />
      <div className="grid min-w-0 gap-1.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <Badge variant="outline">{statusLabel}</Badge>
          {endTime ? (
            <time dateTime={dateTimeAttribute(run.completed_at)} translate="no">
              {tTranscript("run_ended", { time: endTime })}
            </time>
          ) : null}
          {duration ? (
            <span translate="no">
              {tTranscript("run_duration", { duration })}
            </span>
          ) : null}
        </div>
        {run.status === "failed" && run.error ? (
          <div className="grid min-w-0 gap-1 text-sm text-error-foreground">
            <p className="break-words leading-5">{run.error.message}</p>
            <code className="w-fit max-w-full truncate rounded-[5px] bg-error-muted/60 px-1.5 py-0.5 text-[11px]">
              {run.error.code}
            </code>
          </div>
        ) : null}
      </div>
    </section>
  )
}

export function isTerminalRun(
  run: RunView,
): run is TerminalRun {
  return ["completed", "failed", "cancelled"].includes(run.status)
}
