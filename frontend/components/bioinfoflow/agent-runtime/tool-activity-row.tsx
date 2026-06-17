"use client"

import { useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Loader2,
} from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeToolActivity } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

export function ToolActivityRow({ activity }: { activity: AgentRuntimeToolActivity }) {
  const t = useTranslations("agentRuntime")
  const [expanded, setExpanded] = useState(false)
  const hasDetails = Boolean(
    activity.arguments ||
      activity.inputPreview ||
      activity.outputPreview ||
      activity.errorMessage ||
      activity.exitCode !== undefined ||
      activity.relatedFiles.length,
  )

  return (
    <div
      className="grid gap-1.5 text-xs"
      data-testid="agent-tool-activity-row"
    >
      <div className="flex min-w-0 items-center gap-2 text-muted-foreground">
        <ActivityStatusIcon status={activity.status} />
        <span className="min-w-0 flex-1 truncate font-mono text-foreground/80">
          {activity.name}
        </span>
        {activity.summary || activity.inputPreview ? (
          <span className="hidden min-w-0 flex-[1.4] truncate text-muted-foreground sm:block">
            {activity.summary || activity.inputPreview}
          </span>
        ) : null}
        {activity.status !== "completed" ? (
          <span
            className={cn(
              "shrink-0 rounded-full px-1.5 py-0.5 text-[10px]",
              activity.status === "failed" || activity.status === "cancelled" || activity.status === "rejected"
                ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                : "bg-muted text-muted-foreground",
            )}
          >
            {t(`activity.status.${activity.status}`)}
          </span>
        ) : null}
        {hasDetails ? (
          <button
            type="button"
            className="ml-auto inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            <span>{expanded ? t("activity.details.hide") : t("activity.details.show")}</span>
          </button>
        ) : null}
      </div>

      {activity.summary || activity.inputPreview ? (
        <p className="truncate text-muted-foreground sm:hidden">
          {activity.summary || activity.inputPreview}
        </p>
      ) : null}

      {hasDetails && expanded ? (
        <div className="grid gap-2 text-muted-foreground">
          {activity.inputPreview ? <Detail label={t("activity.details.input")} value={activity.inputPreview} /> : null}
          {activity.arguments ? (
            <Detail
              label={t("activity.details.arguments")}
              value={JSON.stringify(activity.arguments, null, 2)}
              pre
            />
          ) : null}
          {activity.outputPreview ? <Detail label={t("activity.details.output")} value={activity.outputPreview} pre /> : null}
          {activity.exitCode !== undefined && activity.exitCode !== null ? (
            <Detail label={t("activity.details.exitCode")} value={String(activity.exitCode)} />
          ) : null}
          {activity.errorMessage ? <Detail label={t("activity.details.error")} value={activity.errorMessage} /> : null}
          {activity.relatedFiles.length ? (
            <Detail
              label={t("activity.details.files")}
              value={activity.relatedFiles.join("\n")}
              pre
            />
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function Detail({ label, value, pre = false }: { label: string; value: string; pre?: boolean }) {
  return (
    <div className="grid gap-1">
      <div className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/80">
        {label}
      </div>
      {pre ? (
        <pre className="max-h-48 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/40 p-2 text-[11px] leading-5 text-foreground/80">
          {value}
        </pre>
      ) : (
        <div className="min-w-0 max-w-full break-words rounded-lg bg-muted/40 p-2 text-[11px] leading-5 text-foreground/80">
          {value}
        </div>
      )}
    </div>
  )
}

function ActivityStatusIcon({ status }: { status: AgentRuntimeToolActivity["status"] }) {
  if (status === "failed" || status === "cancelled" || status === "rejected") {
    return <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
  }
  if (status === "completed") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-muted-foreground/70" />
  }
  if (status === "running" || status === "building") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
  }
  return <Clock3 className={cn("h-3.5 w-3.5 text-muted-foreground")} />
}
