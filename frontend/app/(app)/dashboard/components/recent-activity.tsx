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
  queued: "bg-muted-foreground/50",
  pending: "bg-muted-foreground/50",
};

type RecentActivityProps = {
  recentRuns: DashboardStats["recent_runs"] | undefined;
};

export function RecentActivity({ recentRuns }: RecentActivityProps) {
  const tDashboard = useTranslations("dashboard");
  const tStatus = useTranslations("status");

  return (
    <CardRoot variant="workbench" className="flex min-h-[16rem] flex-1 flex-col">
      <CardHeader
        title={tDashboard("recentActivity")}
        className="border-b-0 !pb-2"
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
      <CardContent className="!pt-0">
        {!recentRuns?.length ? (
          <div className="flex min-h-[8.5rem] items-center justify-center px-4 py-5 text-center">
            <div className="max-w-sm">
              <span className="mx-auto flex size-8 items-center justify-center rounded-md bg-muted/35 text-muted-foreground">
                <Play className="size-3.5" aria-hidden="true" />
              </span>
              <h2 className="mt-3 text-sm font-medium text-foreground">
                {tDashboard("noRecentRuns")}
              </h2>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {tDashboard("noRecentRunsDescription")}
              </p>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-md">
            {recentRuns.map((run) => {
              const config = runStatusLabel[run.status];
              const isFailed = run.status === "failed";
              const badgeVariant = run.status === "queued"
                ? "neutral"
                : runStatusVariant[run.status];
              return (
                <Link
                  key={run.run_id}
                  href={`/runs?highlight=${run.run_id}`}
                  className={cn(
                    "flex items-center gap-3 px-2.5 py-2 text-sm transition-colors hover:bg-muted/35",
                    isFailed && "bg-destructive/[0.04]",
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

                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
                    {run.run_id}
                  </span>

                  {/* Status label */}
                  <StatusBadge
                    variant={badgeVariant}
                    className="shrink-0"
                  >
                    {tStatus(config ?? run.status)}
                  </StatusBadge>

                  {/* Timestamp + duration */}
                  <span className="hidden shrink-0 text-xs text-muted-foreground tabular-nums sm:inline">
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
