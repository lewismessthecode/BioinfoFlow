"use client"

import { useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { Activity, CheckCircle2, XCircle, Clock, type AppIcon } from "@/lib/icons"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useEvents } from "@/hooks/use-events"
import { Progress } from "@/components/ui/progress"
import type { RunStatusEvent } from "@/lib/types"

type StatisticCard = {
  labelKey: "labels.status" | "labels.tasksDone" | "labels.remaining" | "labels.run"
  Icon: AppIcon
  colorClassName: "text-muted-foreground" | "text-success" | "text-destructive"
  getValue: (status: RunStatusEvent | null) => string | number
}

const STATISTIC_CARDS = [
  {
    labelKey: "labels.status",
    Icon: Activity,
    colorClassName: "text-muted-foreground",
    getValue: (status) => status?.status ?? "-",
  },
  {
    labelKey: "labels.tasksDone",
    Icon: CheckCircle2,
    colorClassName: "text-success",
    getValue: (status) => status?.tasks_completed ?? 0,
  },
  {
    labelKey: "labels.remaining",
    Icon: XCircle,
    colorClassName: "text-destructive",
    getValue: (status) =>
      status?.tasks_total
        ? Math.max(status.tasks_total - (status.tasks_completed ?? 0), 0)
        : 0,
  },
  {
    labelKey: "labels.run",
    Icon: Clock,
    colorClassName: "text-muted-foreground",
    getValue: (status) => status?.run_id ?? "-",
  },
] satisfies readonly StatisticCard[]

export function MonitorPanel() {
  const tMonitor = useTranslations("monitor")
  const { activeProjectId } = useProjectContext()
  const [latestStatus, setLatestStatus] = useState<RunStatusEvent | null>(null)

  useEvents({
    projectId: activeProjectId,
    onRunStatus: (event) => {
      setLatestStatus(event.data)
    },
  })

  const progress = useMemo(() => {
    if (!latestStatus?.tasks_total) return 0
    return Math.round(((latestStatus.tasks_completed ?? 0) / latestStatus.tasks_total) * 100)
  }, [latestStatus])

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="text-sm font-medium text-foreground">{tMonitor("title")}</span>
        <div className="flex items-center gap-1.5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping motion-reduce:animate-none absolute inline-flex h-full w-full rounded-full bg-foreground opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-foreground"></span>
          </span>
          <span className="text-xs text-muted-foreground">{tMonitor("live")}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">{tMonitor("currentTask")}</span>
            <span className="font-mono text-xs text-foreground">
              {latestStatus?.current_task || "-"}
            </span>
          </div>
          <Progress value={progress} className="h-1.5" />
          <p className="text-xs text-muted-foreground">
            {tMonitor("progressSummary", {
              completed: latestStatus?.tasks_completed ?? 0,
              total: latestStatus?.tasks_total ?? 0,
            })}
          </p>
        </div>

        <div className="border-t border-border pt-6 space-y-4">
          <h4 className="text-sm font-medium text-foreground">{tMonitor("taskStatus")}</h4>
          <div className="grid grid-cols-2 gap-3">
            {STATISTIC_CARDS.map(({ labelKey, Icon, colorClassName, getValue }) => (
              <div key={labelKey} className="rounded-xl border border-border bg-card p-3">
                <div className={`flex items-center gap-2 ${colorClassName}`}>
                  <Icon className="h-4 w-4" />
                  <span className="text-xs">{tMonitor(labelKey)}</span>
                </div>
                <p className="mt-2 text-2xl font-semibold text-foreground">
                  {getValue(latestStatus)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
