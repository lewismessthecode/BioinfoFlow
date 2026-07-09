"use client"

import "./scheduler.css"

import { useCallback, useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import {
  Activity,
  Gauge,
  RefreshCw,
  ShieldAlert,
} from "@/lib/icons"
import {
  CardContent,
  CardRoot,
} from "@/components/bioinfoflow/card/card-base"
import { StatusBadge } from "@/components/ui/status-badge"
import { Skeleton } from "@/components/ui/skeleton"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { SchedulerStatus } from "@/lib/types"
import { ResourceMonitor } from "./components/resource-monitor"

const REFRESH_INTERVAL_MS = 30_000

function formatUtcTimestamp(value: string | null) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, "0")
  const day = String(date.getUTCDate()).padStart(2, "0")
  const hours = String(date.getUTCHours()).padStart(2, "0")
  const minutes = String(date.getUTCMinutes()).padStart(2, "0")
  return `${year}-${month}-${day} ${hours}:${minutes} UTC`
}

function formatRefreshTimestamp(value: Date | null) {
  if (!value) return "…"
  return formatUtcTimestamp(value.toISOString()) ?? "…"
}

export default function SchedulerPage() {
  const t = useTranslations("scheduler")
  const [status, setStatus] = useState<SchedulerStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const statusRes = await apiRequest<SchedulerStatus>("/scheduler/status")
      setStatus(statusRes.data)
      setLastUpdatedAt(new Date())
    } catch (error) {
      const message = getApiErrorMessage(error, t("errors.loadFailed"))
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }, [t])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  useEffect(() => {
    const interval = setInterval(fetchStatus, REFRESH_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchStatus])

  const isPersistentActive = status?.effective_mode === "persistent"

  if (isLoading) {
    return (
      <div className="bif-workbench-page h-full overflow-y-auto">
        <div className="bif-workbench-page__inner">
          <div className="mb-6 flex flex-col gap-2.5">
            <h1 className="text-2xl font-medium tracking-tight text-foreground">{t("title")}</h1>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{t("subtitle")}</p>
          </div>
          <Skeleton className="h-32 rounded-xl" />
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
            <Skeleton className="h-72 rounded-xl" />
            <Skeleton className="h-72 rounded-xl" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bif-workbench-page h-full overflow-y-auto">
      <div className="bif-workbench-page__inner">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-medium tracking-tight text-foreground">{t("title")}</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              {t("subtitle")}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <StatusBadge variant={isPersistentActive ? "neutral" : "warning"}>
              {isPersistentActive ? (
                <Activity className="h-3 w-3" aria-hidden="true" />
              ) : (
                <ShieldAlert className="h-3 w-3" aria-hidden="true" />
              )}
              {isPersistentActive ? t("status.persistentBadge") : t("status.fallbackBadge")}
            </StatusBadge>
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-2.5 py-1 text-xs font-medium text-muted-foreground">
              <RefreshCw className="h-3 w-3" aria-hidden="true" />
              {t("autoRefresh")}
            </span>
          </div>
        </div>

        {status && (
          <div className="grid gap-4">
            <SchedulerStateStrip
              status={status}
              isPersistentActive={isPersistentActive}
              lastUpdatedAt={lastUpdatedAt}
            />
            <ResourceMonitor schedulerStatus={status} />
          </div>
        )}
      </div>
    </div>
  )
}

function SchedulerStateStrip({
  status,
  isPersistentActive,
  lastUpdatedAt,
}: {
  status: SchedulerStatus
  isPersistentActive: boolean
  lastUpdatedAt: Date | null
}) {
  const t = useTranslations("scheduler")

  return (
    <CardRoot variant="workbench">
      <CardContent className="grid gap-4 !p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:items-center">
        <div className="flex items-start gap-3">
          <div
            className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${
              isPersistentActive
                ? "border-border bg-muted text-muted-foreground"
                : "border-warning-border bg-warning-muted text-warning"
            }`}
          >
            <Gauge className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-medium text-foreground">
                {isPersistentActive
                  ? t("status.activeTitle")
                  : t("status.fallbackTitle")}
              </h2>
              <StatusBadge variant={isPersistentActive ? "neutral" : "warning"}>
                {isPersistentActive ? t("status.ready") : t("status.attention")}
              </StatusBadge>
            </div>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              {isPersistentActive ? t("status.activeBody") : t("status.fallbackBody")}
            </p>
          </div>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4">
          <StateMetric label={t("queueDepth")} value={status.queue_depth} />
          <StateMetric label={t("workers")} value={status.workers} />
          <StateMetric label={t("queued")} value={status.states.queued} />
          <StateMetric label={t("dispatched")} value={status.states.dispatched} />
          <StateMetric label={t("completed")} value={status.states.completed} />
          <StateMetric label={t("failed")} value={status.states.failed} />
          <StateMetric label={t("mode")} value={status.effective_mode} />
          <StateMetric
            label={t("snapshot")}
            value={formatRefreshTimestamp(lastUpdatedAt)}
            muted
          />
        </div>
      </CardContent>
    </CardRoot>
  )
}

function StateMetric({
  label,
  value,
  muted,
}: {
  label: string
  value: string | number
  muted?: boolean
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2">
      <p className="truncate text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-1 truncate font-mono text-xs font-medium sm:text-sm ${
          muted ? "text-muted-foreground" : "text-foreground"
        }`}
      >
        {value}
      </p>
    </div>
  )
}
