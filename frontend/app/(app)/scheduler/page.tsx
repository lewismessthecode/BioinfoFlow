"use client"

import "./scheduler.css"

import { useCallback, useEffect, useState } from "react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Gauge,
  Layers,
  RefreshCw,
  ShieldAlert,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import {
  CardContent,
  CardHeader,
  CardRoot,
} from "@/components/bioinfoflow/card/card-base"
import { StatusBadge } from "@/components/ui/status-badge"
import { Skeleton } from "@/components/ui/skeleton"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { SchedulerStatus } from "@/lib/types"
import { ResourceMonitor } from "./components/resource-monitor"

const REFRESH_INTERVAL_MS = 30_000

type StatKey = "queued" | "dispatched" | "completed" | "failed"

type StatItem = {
  key: StatKey
  icon: LucideIcon
  variant: "neutral" | "warning" | "info" | "success" | "destructive"
  value: number
}

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

  const statItems: StatItem[] = [
    {
      key: "queued",
      icon: Clock,
      variant: status && status.states.queued > 0 ? "warning" : "neutral",
      value: status?.states.queued ?? 0,
    },
    {
      key: "dispatched",
      icon: Layers,
      variant: status && status.states.dispatched > 0 ? "info" : "neutral",
      value: status?.states.dispatched ?? 0,
    },
    {
      key: "completed",
      icon: CheckCircle2,
      variant: "neutral",
      value: status?.states.completed ?? 0,
    },
    {
      key: "failed",
      icon: AlertTriangle,
      variant: status && status.states.failed > 0 ? "destructive" : "neutral",
      value: status?.states.failed ?? 0,
    },
  ]

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-6">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">{t("subtitle")}</p>
          </div>
          <Skeleton className="h-32 rounded-xl" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
            <Skeleton className="h-72 rounded-xl lg:col-span-5" />
            <Skeleton className="h-72 rounded-xl lg:col-span-7" />
            <Skeleton className="h-56 rounded-xl lg:col-span-5" />
            <Skeleton className="h-56 rounded-xl lg:col-span-7" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-0.5 max-w-2xl text-sm leading-6 text-muted-foreground">
              {t("subtitle")}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <StatusBadge variant={isPersistentActive ? "success" : "warning"}>
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
          <>
            <SchedulerStateStrip
              status={status}
              isPersistentActive={isPersistentActive}
              lastUpdatedAt={lastUpdatedAt}
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {statItems.map((item) => (
                <QueueMetricCard key={item.key} item={item} />
              ))}
            </div>
          </>
        )}

        <ResourceMonitor schedulerStatus={status} />
        <GuidanceCard />
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
    <CardRoot>
      <CardContent className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="flex items-start gap-4">
          <div
            className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${
              isPersistentActive
                ? "border-success-border bg-success-muted text-success"
                : "border-warning-border bg-warning-muted text-warning"
            }`}
          >
            <Gauge className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-foreground">
                {isPersistentActive
                  ? t("status.activeTitle")
                  : t("status.fallbackTitle")}
              </h2>
              <StatusBadge variant={isPersistentActive ? "success" : "warning"}>
                {isPersistentActive ? t("status.ready") : t("status.attention")}
              </StatusBadge>
            </div>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              {isPersistentActive ? t("status.activeBody") : t("status.fallbackBody")}
            </p>
          </div>
        </div>

        <div className="grid min-w-0 grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[440px]">
          <StateMetric label={t("mode")} value={status.effective_mode} />
          <StateMetric label={t("workers")} value={status.workers} />
          <StateMetric label={t("queueDepth")} value={status.queue_depth} />
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
    <div className="rounded-lg border border-border/70 bg-muted/25 px-3 py-2.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={`mt-1 break-words font-mono text-xs font-medium sm:text-sm ${
          muted ? "text-muted-foreground" : "text-foreground"
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function QueueMetricCard({ item }: { item: StatItem }) {
  const t = useTranslations("scheduler")
  const Icon = item.icon

  return (
    <CardRoot>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-muted-foreground">{t(item.key)}</p>
          <StatusBadge variant={item.variant} className="px-2 py-1">
            <Icon className="h-3.5 w-3.5" />
            <span className="sr-only">{t(item.key)}</span>
          </StatusBadge>
        </div>
        <div className="text-3xl font-semibold tracking-tight text-foreground">
          {item.value}
        </div>
        <p className="min-h-10 text-xs leading-5 text-muted-foreground">
          {t(`cardDescriptions.${item.key}`)}
        </p>
      </CardContent>
    </CardRoot>
  )
}

function GuidanceCard() {
  const t = useTranslations("scheduler")
  const items = [
    { title: t("guidance.queueTitle"), body: t("guidance.queueBody") },
    { title: t("guidance.dispatchTitle"), body: t("guidance.dispatchBody") },
    { title: t("guidance.resourcesTitle"), body: t("guidance.resourcesBody") },
  ]

  return (
    <CardRoot className="bg-card/70">
      <CardHeader title={t("guidance.title")} />
      <CardContent className="space-y-4 p-5">
        <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
          {t("guidance.body")}
        </p>
        <div className="grid gap-3 md:grid-cols-3">
          {items.map((item) => (
            <div key={item.title} className="rounded-lg border border-border/70 bg-muted/20 p-3">
              <p className="text-sm font-medium text-foreground">{item.title}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{item.body}</p>
            </div>
          ))}
        </div>
      </CardContent>
    </CardRoot>
  )
}
