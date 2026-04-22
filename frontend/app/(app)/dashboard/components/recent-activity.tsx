"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Play, ArrowRight } from "lucide-react";
import {
  CardRoot,
  CardContent,
  CardHeader,
} from "@/components/bioinfoflow/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatDateTime, formatDuration } from "@/lib/format-utils";
import { runStatusLabel, runStatusVariant } from "@/constants/status-config";
import type { DashboardStats } from "./dashboard-types";

const statusDotColor: Record<string, string> = {
  completed: "bg-success",
  failed: "bg-destructive",
  running: "bg-info animate-pulse motion-reduce:animate-none",
  cancelled: "bg-muted-foreground/50",
  queued: "bg-warning",
  pending: "bg-muted-foreground/50",
};

type RecentActivityProps = {
  recentRuns: DashboardStats["recent_runs"] | undefined;
};

export function RecentActivity({ recentRuns }: RecentActivityProps) {
  const tDashboard = useTranslations("dashboard");
  const tStatus = useTranslations("status");

  return (
    <CardRoot className="mb-5 flex-1 flex flex-col">
      <CardHeader
        title={tDashboard("recentActivity")}
        action={
          <Button variant="ghost" size="sm" asChild>
            <Link
              href="/runs?scope=all"
              className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
              {tDashboard("viewAll")}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        }
      />
      <CardContent>
        {!recentRuns?.length ? (
          <EmptyState
            icon={Play}
            title={tDashboard("noRecentRuns")}
            description={tDashboard("noRecentRunsDescription")}
            className="py-8"
          />
        ) : (
          <div className="space-y-1">
            {recentRuns.map((run) => {
              const config = runStatusLabel[run.status];
              const isFailed = run.status === "failed";
              return (
                <Link
                  key={run.run_id}
                  href={`/runs?highlight=${run.run_id}`}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-muted/50",
                    isFailed && "bg-destructive/[0.03]",
                  )}
                >
                  {/* Status dot */}
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full flex-shrink-0",
                      statusDotColor[run.status] ?? "bg-muted-foreground/50",
                    )}
                    aria-label={tStatus(config ?? run.status)}
                    role="img"
                  />

                  <span className="font-mono text-xs text-foreground truncate min-w-0 flex-1">
                    {run.run_id}
                  </span>

                  {/* Status label */}
                  <StatusBadge
                    variant={runStatusVariant[run.status]}
                    className="flex-shrink-0"
                  >
                    {tStatus(config ?? run.status)}
                  </StatusBadge>

                  {/* Timestamp + duration */}
                  <span className="text-xs text-muted-foreground flex-shrink-0 tabular-nums">
                    {formatDateTime(run.started_at)}
                    {run.duration_seconds != null &&
                      ` · ${formatDuration(run.duration_seconds)}`}
                  </span>
                </Link>
              );
            })}
          </div>
        )}
      </CardContent>
    </CardRoot>
  );
}
