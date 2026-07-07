"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Gauge, ArrowRight } from "lucide-react";
import {
  CardRoot,
  CardContent,
  CardHeader,
} from "@/components/bioinfoflow/card";
import type { SchedulerStatus } from "@/lib/types";

type SchedulerSummaryProps = {
  schedulerStatus: SchedulerStatus;
};

export function SchedulerSummary({ schedulerStatus }: SchedulerSummaryProps) {
  const tDashboard = useTranslations("dashboard");

  return (
    <Link href="/scheduler" className="group block">
      <CardRoot
        variant="workbench"
        data-interactive="true"
        className="flex flex-1 cursor-pointer flex-col"
      >
        <CardHeader
          title={tDashboard("schedulerCard.title")}
          icon={Gauge}
          className="border-b-0"
          action={
            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground transition-colors" />
          }
        />
        <CardContent>
          <div className="flex flex-col gap-4 text-sm sm:flex-row sm:items-center sm:gap-6">
            <div className="bif-workbench-panel px-3 py-2">
              <p className="mb-0.5 text-xs font-medium text-muted-foreground">
                {tDashboard("schedulerCard.queueDepth")}
              </p>
              <p className="font-mono text-2xl font-semibold text-foreground tabular-nums">
                {schedulerStatus.queue_depth}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
              <span className="metadata-pill flex items-center gap-1.5 rounded-md border px-2 py-1">
                <span className="font-mono font-medium text-foreground tabular-nums">
                  {schedulerStatus.states.queued}
                </span>{" "}
                {tDashboard("schedulerCard.states.queued")}
              </span>
              <span className="metadata-pill flex items-center gap-1.5 rounded-md border px-2 py-1">
                <span className="font-mono font-medium text-foreground tabular-nums">
                  {schedulerStatus.states.dispatched}
                </span>{" "}
                {tDashboard("schedulerCard.states.dispatched")}
              </span>
              <span className="metadata-pill flex items-center gap-1.5 rounded-md border px-2 py-1">
                <span className="font-mono font-medium text-foreground tabular-nums">
                  {schedulerStatus.states.completed}
                </span>{" "}
                {tDashboard("schedulerCard.states.completed")}
              </span>
            </div>
          </div>
        </CardContent>
      </CardRoot>
    </Link>
  );
}
