"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
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

  const prefersReducedMotion = useReducedMotion();
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

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const minLoadTime = new Promise((resolve) => setTimeout(resolve, 500));

      const [[statsRes, healthRes, gpuRes, schedulerRes, readinessRes]] = await Promise.all([
        Promise.all([
          apiRequest<DashboardStats>("/stats"),
          apiRequest<SystemHealth>("/system/health"),
          apiRequest<GpuInfo>("/system/gpu"),
          apiRequest<SchedulerStatus>("/scheduler/status").catch(() => null),
          apiRequest<ReadinessStatus>("/system/readiness").catch(() => null),
        ]),
        minLoadTime,
      ]);

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
      <div className="h-full overflow-y-auto">
        <div className="p-4 sm:p-6 max-w-6xl mx-auto">
          <div className="mb-5">
            <h1 className="text-xl font-semibold text-foreground">
              {greeting}
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {tDashboard("subtitle")}
            </p>
          </div>
          <DashboardSkeleton />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-foreground">{greeting}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
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

        <ReadinessCenter readiness={readiness} onRefresh={fetchData} />

        <motion.div
          initial={prefersReducedMotion ? {} : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.05 }}
        >
          <StatCards stats={stats} />
        </motion.div>
        <motion.div
          initial={prefersReducedMotion ? {} : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.15 }}
        >
          <RecentActivity recentRuns={stats?.recent_runs} />
        </motion.div>
        <motion.div
          initial={prefersReducedMotion ? {} : { opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.25 }}
        >
          <SystemStatus health={health} gpuInfo={gpuInfo} />
        </motion.div>
        {schedulerStatus && (
          <motion.div
            initial={prefersReducedMotion ? {} : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.35 }}
          >
            <SchedulerSummary schedulerStatus={schedulerStatus} />
          </motion.div>
        )}
      </div>
    </div>
  );
}
