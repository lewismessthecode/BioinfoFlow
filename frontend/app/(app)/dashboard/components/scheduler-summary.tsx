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
    <Link
      href="/scheduler"
      className="group block h-full rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2"
    >
      <CardRoot variant="workbench" className="flex h-full flex-1 flex-col transition-colors group-hover:bg-muted/30">
        <CardHeader
          title={tDashboard("schedulerCard.title")}
          icon={Gauge}
          className="border-b-0 !pb-2"
          action={
            <span
              className="flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors group-hover:text-foreground"
              aria-hidden="true"
            >
              <ArrowRight className="size-3.5" />
            </span>
          }
        />
        <CardContent className="flex flex-1 flex-col justify-between gap-4 !pt-0">
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
        </CardContent>
      </CardRoot>
    </Link>
  );
}
