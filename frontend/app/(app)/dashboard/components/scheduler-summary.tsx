"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Gauge, ArrowRight } from "lucide-react";
import {
  CardRoot,
  CardContent,
  CardHeader,
} from "@/components/bioinfoflow/card";
import { Button } from "@/components/ui/button";
import type { SchedulerStatus } from "@/lib/types";

type SchedulerSummaryProps = {
  schedulerStatus: SchedulerStatus;
};

export function SchedulerSummary({ schedulerStatus }: SchedulerSummaryProps) {
  const tDashboard = useTranslations("dashboard");

  return (
    <CardRoot variant="workbench" className="flex h-full flex-1 flex-col">
      <CardHeader
        title={tDashboard("schedulerCard.title")}
        icon={Gauge}
        className="border-b-0 !pb-2"
        action={
          <Button variant="ghost" size="icon-sm" asChild>
            <Link
              href="/scheduler"
              aria-label={tDashboard("schedulerCard.title")}
              className="text-muted-foreground hover:text-foreground"
            >
              <ArrowRight className="size-3.5" aria-hidden="true" />
            </Link>
          </Button>
        }
      />
      <CardContent className="flex flex-1 flex-col justify-between gap-5 !pt-0">
        <div>
          <p className="text-xs font-medium text-muted-foreground">
            {tDashboard("schedulerCard.queueDepth")}
          </p>
          <p className="mt-1 font-mono text-3xl font-semibold tracking-tight text-foreground tabular-nums">
            {schedulerStatus.queue_depth}
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 text-xs text-muted-foreground">
          <span className="min-w-0">
            <span className="block font-mono font-medium text-foreground tabular-nums">
              {schedulerStatus.states.queued}
            </span>
            <span className="block truncate">
              {tDashboard("schedulerCard.states.queued")}
            </span>
          </span>
          <span className="min-w-0">
            <span className="block font-mono font-medium text-foreground tabular-nums">
              {schedulerStatus.states.dispatched}
            </span>
            <span className="block truncate">
              {tDashboard("schedulerCard.states.dispatched")}
            </span>
          </span>
          <span className="min-w-0">
            <span className="block font-mono font-medium text-foreground tabular-nums">
              {schedulerStatus.states.completed}
            </span>
            <span className="block truncate">
              {tDashboard("schedulerCard.states.completed")}
            </span>
          </span>
        </div>
      </CardContent>
    </CardRoot>
  );
}
