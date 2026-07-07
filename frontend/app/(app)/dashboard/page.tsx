"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { apiRequest, getApiErrorMessage } from "@/lib/api";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import type { SchedulerStatus } from "@/lib/types";
import { getTimePeriod } from "@/lib/time-greeting";
import { authClient } from "@/lib/auth-client";
import {
  buildNarrative,
  type DashboardStats,
  type SystemHealth,
  type GpuInfo,
  type ReadinessStatus,
} from "./components/dashboard-types";
import { DashboardSkeleton } from "./components/dashboard-skeleton";
import { StatCards } from "./components/stat-cards";
import { RecentActivity } from "./components/recent-activity";
import { SystemStatus } from "./components/system-status";
import { SchedulerSummary } from "./components/scheduler-summary";
import { ReadinessCenter } from "./components/readiness-center";

export default function DashboardPage() {
  const tDashboard = useTranslations("dashboard");
  const tGreeting = useTranslations("greeting");
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [gpuInfo, setGpuInfo] = useState<GpuInfo | null>(null);
  const [schedulerStatus, setSchedulerStatus] =
    useState<SchedulerStatus | null>(null);
  const [readiness, setReadiness] = useState<ReadinessStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const { data: session } = authClient.useSession();
  const userName = session?.user?.name;
  const firstName = userName?.split(/\s+/)[0] || "";
  const period = getTimePeriod();
  const dashboardKey =
    `dashboard${period.charAt(0).toUpperCase()}${period.slice(1)}` as
      | "dashboardMorning"
      | "dashboardAfternoon"
      | "dashboardEvening"
      | "dashboardLateNight";
  const greeting = tGreeting(dashboardKey, { name: firstName });
  const monitoringOverviewLabel = tDashboard("monitoringOverview");

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const minLoadTime = new Promise((resolve) => setTimeout(resolve, 500));

      const dashboardRequests = Promise.all([
        apiRequest<DashboardStats>("/stats"),
        apiRequest<SystemHealth>("/system/health"),
        apiRequest<GpuInfo>("/system/gpu"),
        apiRequest<SchedulerStatus>("/scheduler/status").catch(() => null),
        apiRequest<ReadinessStatus>("/system/readiness").catch(() => null),
      ]);
      const [
        [statsRes, healthRes, gpuRes, schedulerRes, readinessRes],
      ] = await Promise.all([dashboardRequests, minLoadTime]);

      setStats(statsRes.data);
      setHealth(healthRes.data);
      setGpuInfo(gpuRes.data);
      setSchedulerStatus(schedulerRes?.data ?? null);
      setReadiness(readinessRes?.data ?? null);
    } catch (error) {
      const message = getApiErrorMessage(error, tDashboard("errors.loadFailed"));
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [tDashboard]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (isLoading) {
    return (
      <div className="bif-workbench-page h-full overflow-y-auto">
        <section
          aria-label={monitoringOverviewLabel}
          data-dashboard-surface="monitoring"
          className="bif-workbench-page__inner"
        >
          <div className="mb-5 flex flex-col gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">
              {greeting}
            </h1>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              {tDashboard("subtitle")}
            </p>
          </div>
          <DashboardSkeleton />
        </section>
      </div>
    );
  }

  return (
    <div className="bif-workbench-page h-full overflow-y-auto">
      <section
        aria-label={monitoringOverviewLabel}
        data-dashboard-surface="monitoring"
        className="bif-workbench-page__inner"
      >
        <div className="mb-5 flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {greeting}
          </h1>
          <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
            {stats ? buildNarrative(stats, tDashboard) : tDashboard("subtitle")}
          </p>
        </div>

        {health && !health.docker.available && (
          <Alert variant="destructive" className="mb-4">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{tDashboard("dockerUnavailableTitle")}</AlertTitle>
            <AlertDescription>
              {tDashboard("dockerUnavailableDescription")}
            </AlertDescription>
          </Alert>
        )}

        <div className="grid gap-3">
          <ReadinessCenter readiness={readiness} onRefresh={fetchData} />

          <StatCards stats={stats} />

          <div
            className={
              schedulerStatus
                ? "grid items-stretch gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(18rem,0.75fr)]"
                : "grid items-start gap-3"
            }
          >
            <div className="min-w-0 h-full">
              <SystemStatus
                health={health}
                gpuInfo={gpuInfo}
              />
            </div>
            {schedulerStatus && (
              <div className="min-w-0 h-full">
                <SchedulerSummary schedulerStatus={schedulerStatus} />
              </div>
            )}
          </div>

          <div className="min-w-0">
            <RecentActivity recentRuns={stats?.recent_runs} />
          </div>
        </div>
      </section>
    </div>
  );
}
