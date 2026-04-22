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
    <Link href="/scheduler">
      <CardRoot className="mb-5 flex-1 flex flex-col">
        <CardHeader
          title={tDashboard("schedulerCard.title")}
          icon={Gauge}
          action={
            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground transition-colors" />
          }
        />
        <CardContent>
          <div className="flex items-center gap-6 text-sm">
            <div>
              <p className="text-xs text-muted-foreground uppercase tracking-wider mb-0.5">
                {tDashboard("schedulerCard.queueDepth")}
              </p>
              <p className="text-lg font-semibold text-foreground font-mono">
                {schedulerStatus.queue_depth}
              </p>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>
                <span className="font-medium text-foreground">
                  {schedulerStatus.states.queued}
                </span>{" "}
                queued
              </span>
              <span>
                <span className="font-medium text-foreground">
                  {schedulerStatus.states.dispatched}
                </span>{" "}
                dispatched
              </span>
              <span>
                <span className="font-medium text-foreground">
                  {schedulerStatus.states.completed}
                </span>{" "}
                completed
              </span>
            </div>
          </div>
        </CardContent>
      </CardRoot>
    </Link>
  );
}
