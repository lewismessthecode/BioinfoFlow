"use client"

import { useCallback, useEffect, useState } from "react"
import { useTranslations } from "next-intl"
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
import { toast } from "sonner"
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
  if (!value) return "..."
  return formatUtcTimestamp(value.toISOString()) ?? "..."
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

  const statItems = [
    { key: "queued", icon: Clock, variant: "warning" as const, value: status?.states.queued ?? 0 },
    { key: "dispatched", icon: Layers, variant: "info" as const, value: status?.states.dispatched ?? 0 },
    { key: "completed", icon: CheckCircle2, variant: "success" as const, value: status?.states.completed ?? 0 },
    { key: "failed", icon: AlertTriangle, variant: "destructive" as const, value: status?.states.failed ?? 0 },
  ]

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="mx-auto max-w-5xl space-y-5 p-6">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">{t("subtitle")}</p>
          </div>
          <Skeleton className="h-36 rounded-xl" />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
          <Skeleton className="h-80 rounded-xl" />
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-6 p-6">
        {/* ── Header ───────────────────────────────── */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-foreground">{t("title")}</h1>
            <p className="mt-0.5 max-w-lg text-[13px] leading-6 text-muted-foreground">
              {t("subtitle")}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <StatusBadge variant={isPersistentActive ? "success" : "warning"}>
              {isPersistentActive ? <Activity className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
              {status?.effective_mode ?? "legacy"}
            </StatusBadge>
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-border/60 bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
              <RefreshCw className="h-3 w-3" />
              {t("autoRefresh")}
            </span>
          </div>
        </div>

        {/* ── Status banner + inline stats ─────────── */}
        {status && (
          <div className="rounded-xl border border-border/60 bg-card">
            <div className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted/60">
                  <Gauge className="h-4 w-4 text-muted-foreground" />
                </div>
                <div>
                  <h2 className="text-sm font-medium text-foreground">
                    {isPersistentActive
                      ? t("status.activeTitle")
                      : t("status.fallbackTitle")}
                  </h2>
                  <p className="mt-0.5 max-w-xl text-[13px] leading-5 text-muted-foreground">
                    {isPersistentActive
                      ? t("status.activeBody")
                      : t("status.fallbackBody")}
                  </p>
                </div>
              </div>

              <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted-foreground lg:gap-x-6">
                <div>
                  <span className="text-[10px] uppercase tracking-[0.14em]">{t("mode")}</span>
                  <p className="mt-0.5 font-medium text-foreground">{status.effective_mode}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase tracking-[0.14em]">{t("workers")}</span>
                  <p className="mt-0.5 font-mono font-medium text-foreground">{status.workers}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase tracking-[0.14em]">{t("queueDepth")}</span>
                  <p className="mt-0.5 font-mono font-medium text-foreground">{status.queue_depth}</p>
                </div>
                <div>
                  <span className="text-[10px] uppercase tracking-[0.14em]">{t("snapshot")}</span>
                  <p className="mt-0.5 font-mono text-muted-foreground">
                    {formatRefreshTimestamp(lastUpdatedAt)}
                  </p>
                </div>
              </div>
            </div>

            {/* Stat counters row */}
            <div className="grid grid-cols-2 border-t border-border/50 lg:grid-cols-4">
              {statItems.map((item) => {
                const Icon = item.icon
                return (
                  <div
                    key={item.key}
                    className="flex items-center gap-3 border-b border-r border-border/50 px-5 py-4 last:border-r-0 lg:border-b-0 [&:nth-child(2)]:border-r-0 lg:[&:nth-child(2)]:border-r"
                  >
                    <StatusBadge variant={item.variant} className="shrink-0">
                      <Icon className="h-3 w-3" />
                    </StatusBadge>
                    <div className="min-w-0">
                      <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                        {t(item.key)}
                      </p>
                      <p className="text-lg font-semibold tracking-tight text-foreground">
                        {item.value}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* ── Live resource monitor ─────────────────── */}
        <ResourceMonitor />

        {/* ── Guidance ─────────────────────────────── */}
        <div className="rounded-xl border border-border/60 bg-card">
          <div className="border-b border-border/50 px-5 py-3">
            <span className="text-sm font-medium text-foreground">{t("guidance.title")}</span>
          </div>
          <div className="p-5">
            <p className="mb-4 text-xs leading-5 text-muted-foreground">{t("guidance.body")}</p>
            <div className="space-y-0.5">
              {[
                { title: t("guidance.queueTitle"), body: t("guidance.queueBody") },
                { title: t("guidance.dispatchTitle"), body: t("guidance.dispatchBody") },
                { title: t("guidance.resourcesTitle"), body: t("guidance.resourcesBody") },
              ].map((item) => (
                <div key={item.title} className="rounded-lg px-3 py-2.5">
                  <p className="text-[13px] font-medium text-foreground">{item.title}</p>
                  <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{item.body}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
