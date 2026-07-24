"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { CardRoot } from "@/components/bioinfoflow/card";
import { Gauge, ArrowRight } from "@/lib/icons";
import type { SchedulerStatus } from "@/lib/types";

type SchedulerSummaryProps = {
  schedulerStatus: SchedulerStatus;
};

export function SchedulerSummary({ schedulerStatus }: SchedulerSummaryProps) {
  const tDashboard = useTranslations("dashboard");

  return (
    <CardRoot variant="workbench" className="h-full min-w-0">
      <Link
        href="/scheduler"
        data-dashboard-section="scheduler"
        data-testid="dashboard-scheduler-section"
        className="group block h-full min-w-0 rounded-[inherit] p-4 transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/30"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-foreground">
            <Gauge className="size-3.5 text-muted-foreground/80" />
            <h2 className="text-sm font-medium">{tDashboard("schedulerCard.title")}</h2>
          </div>
          <ArrowRight className="size-3.5 text-muted-foreground transition-colors group-hover:text-foreground" aria-hidden="true" />
        </div>
        <div className="mt-4 flex flex-col justify-between gap-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              {tDashboard("schedulerCard.queueDepth")}
            </p>
            <p className="mt-1 font-mono text-2xl font-medium tracking-tight text-foreground tabular-nums">
              {schedulerStatus.queue_depth}
            </p>
          </div>
          <div className="grid gap-2 text-xs text-muted-foreground">
            <span className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2">
              <span className="truncate">
                {tDashboard("schedulerCard.states.queued")}
              </span>
              <span className="font-mono font-medium text-foreground tabular-nums">
                {schedulerStatus.states.queued}
              </span>
            </span>
            <span className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2">
              <span className="truncate">
                {tDashboard("schedulerCard.states.dispatched")}
              </span>
              <span className="font-mono font-medium text-foreground tabular-nums">
                {schedulerStatus.states.dispatched}
              </span>
            </span>
            <span className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2">
              <span className="truncate">
                {tDashboard("schedulerCard.states.completed")}
              </span>
              <span className="font-mono font-medium text-foreground tabular-nums">
                {schedulerStatus.states.completed}
              </span>
            </span>
          </div>
        </div>
      </Link>
    </CardRoot>
  );
}
