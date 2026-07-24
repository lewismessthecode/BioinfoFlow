"use client";

/* Hallmark · pre-emit critique: P5 H4 E5 S5 R5 V4 */
/* Hallmark · macrostructure: flat-operations-strip · genre: modern-minimal · tone: restrained · anchor: existing semantic tokens · contrast: pass (40–41) · mobile: pass (34, 49, 50–57) */

import { CardRoot } from "@/components/bioinfoflow/card";
import type { SchedulerStatus } from "@/lib/types";
import type { GpuInfo, SystemHealth } from "./dashboard-types";
import { SchedulerSummary } from "./scheduler-summary";
import { SystemStatus } from "./system-status";

type OperationsOverviewProps = {
  health: SystemHealth | null;
  gpuInfo: GpuInfo | null;
  schedulerStatus: SchedulerStatus | null;
};

export function OperationsOverview({ health, gpuInfo, schedulerStatus }: OperationsOverviewProps) {
  return (
    <CardRoot
      variant="workbench"
      data-testid="dashboard-operations-overview"
      data-layout="flat-sections"
      className="grid overflow-hidden xl:grid-cols-[0.8fr_minmax(0,1.35fr)_0.9fr]"
    >
      <SystemStatus health={health} gpuInfo={gpuInfo} />
      {schedulerStatus ? <SchedulerSummary schedulerStatus={schedulerStatus} /> : null}
    </CardRoot>
  );
}
