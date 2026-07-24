"use client";

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
    <div
      data-testid="dashboard-operations-overview"
      data-layout="card-grid"
      className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
    >
      <SystemStatus health={health} gpuInfo={gpuInfo} />
      {schedulerStatus ? <SchedulerSummary schedulerStatus={schedulerStatus} /> : null}
    </div>
  );
}
