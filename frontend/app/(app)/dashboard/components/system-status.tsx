"use client";

import { useTranslations } from "next-intl";
import {
  Container,
  Cpu,
  HardDrive,
} from "@/lib/icons";
import { CardRoot } from "@/components/bioinfoflow/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import type { SystemHealth, GpuInfo } from "./dashboard-types";

type SystemStatusProps = {
  health: SystemHealth | null;
  gpuInfo: GpuInfo | null;
};

function hasNvidiaSignal(health: SystemHealth | null, gpuInfo: GpuInfo | null): boolean {
  return Boolean(
    gpuInfo?.nvidia_smi_found ||
      gpuInfo?.docker_nvidia_runtime ||
      health?.docker.nvidia_runtime ||
      gpuInfo?.gpus.some((gpu) => gpu.gpu_type === "NVIDIA"),
  );
}

function gpuSummaryVariant(gpuInfo: GpuInfo | null) {
  if (gpuInfo?.usable_for_gpu_workflows) return "success";
  return "neutral";
}

function aggregateGpuModels(gpus: GpuInfo["gpus"]): string[] {
  const counts = new Map<string, number>();
  for (const gpu of gpus) counts.set(gpu.name, (counts.get(gpu.name) ?? 0) + 1);
  return Array.from(counts, ([name, count]) => count > 1 ? `${count} × ${name}` : name);
}

const gpuStateCopy: Record<string, string> = {
  disabled: "gpu.stateDisabled",
  docker_unavailable: "gpu.stateDockerUnavailable",
  toolkit_unavailable: "gpu.stateToolkitUnavailable",
  no_gpus: "gpu.stateNoGpus",
  policy_invalid: "gpu.statePolicyInvalid",
  probe_failed: "gpu.stateProbeFailed",
};

export function SystemStatus({ health, gpuInfo }: SystemStatusProps) {
  const tDashboard = useTranslations("dashboard");
  const gpuRows = gpuInfo?.gpus ?? [];
  const nvidiaSignal = hasNvidiaSignal(health, gpuInfo);
  const showNoGpu = !gpuInfo?.available && gpuRows.length === 0 && !nvidiaSignal;
  const detectedCount = gpuInfo?.detected_count ?? gpuRows.length;
  const selectedCount = gpuInfo?.selected_count ?? gpuRows.filter((gpu) => gpu.selected !== false).length;
  const selectedUuids = gpuInfo?.selected_gpu_uuids ?? gpuRows.filter((gpu) => gpu.selected).flatMap((gpu) => gpu.uuid ? [gpu.uuid] : []);
  const hasNvidiaGpu = gpuRows.some((gpu) => gpu.gpu_type === "NVIDIA");
  const policyLabel = gpuInfo?.mode === "manual"
    ? tDashboard("gpu.policyManual", { selected: selectedCount, detected: detectedCount })
    : gpuInfo?.mode === "disabled"
      ? tDashboard("gpu.policyDisabled")
      : tDashboard("gpu.policyAuto", { selected: selectedCount, detected: detectedCount });
  const ready = Boolean(gpuInfo?.usable_for_gpu_workflows);
  const stateCopyKey = gpuInfo?.state ? gpuStateCopy[gpuInfo.state] : undefined;
  const firstSelectedUuid = selectedUuids[0];
  const additionalSelectedUuidCount = Math.max(selectedUuids.length - 1, 0);

  return (
    <>
      <CardRoot variant="workbench" className="h-full min-w-0">
        <section data-dashboard-section="docker" data-testid="dashboard-docker-section" className="p-4">
          <span className="sr-only">{tDashboard("systemStatus")}</span>
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-foreground">
              <Container className="size-3.5 text-muted-foreground/80" />
              <h2 className="text-sm font-medium">{tDashboard("dockerAvailable")}</h2>
            </div>
            <StatusBadge
              variant={health?.docker.available ? "neutral" : "destructive"}
            >
              {health?.docker.available
                ? tDashboard("healthy")
                : tDashboard("unavailable")}
            </StatusBadge>
          </div>
          <dl className="mt-4 grid gap-2.5 text-sm">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2.5">
              <dt className="truncate text-muted-foreground">{tDashboard("docker.badgePrefix")}</dt>
              <dd className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span className={cn("size-1.5 rounded-full", health?.docker.available ? "bg-muted-foreground/60" : "bg-destructive")} />
                {health?.docker.available ? tDashboard("docker.available") : tDashboard("docker.notRunning")}
              </dd>
            </div>
          </dl>
        </section>
      </CardRoot>

      <CardRoot variant="workbench" className="h-full min-w-0">
        <section data-dashboard-section="gpu" data-testid="dashboard-gpu-section" className="p-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-foreground">
              <Cpu className="size-3.5 text-muted-foreground/80" />
              <h2 className="text-sm font-medium">{tDashboard("gpuStatus")}</h2>
            </div>
            {ready || nvidiaSignal ? (
              <StatusBadge variant={gpuSummaryVariant(gpuInfo)}>
                {ready ? tDashboard("gpu.ready") : tDashboard("gpu.nvidiaRuntimeVisible")}
              </StatusBadge>
            ) : null}
          </div>
          <div className="mt-4 grid gap-2.5 text-sm">
            {aggregateGpuModels(gpuRows).map((model) => (
              <div key={model} className="border-t border-border/70 pt-2.5 text-muted-foreground">{model}</div>
            ))}
            {gpuInfo?.mode && (hasNvidiaGpu || selectedCount > 0) ? (
              <div className="border-t border-border/70 pt-2.5 text-xs text-muted-foreground">{policyLabel}</div>
            ) : null}
            {stateCopyKey ? (
              <div className="border-t border-border/70 pt-2.5 text-xs leading-5 text-muted-foreground">
                {tDashboard(stateCopyKey)}
              </div>
            ) : null}
            {gpuInfo?.stale ? (
              <div className="border-t border-border/70 pt-2.5 text-xs text-muted-foreground">
                {tDashboard("gpu.stale")}
              </div>
            ) : null}
            {firstSelectedUuid ? (
              <div className="min-w-0 border-t border-border/70 pt-2.5 text-xs">
                <div className="text-muted-foreground">{tDashboard("gpu.selectedDeviceIds")}</div>
                <div className="mt-1.5 flex min-w-0 items-center gap-2">
                  <code
                    className="min-w-0 flex-1 truncate font-mono text-foreground"
                    title={selectedUuids.join(", ")}
                  >
                    {firstSelectedUuid}
                  </code>
                  {additionalSelectedUuidCount > 0 ? (
                    <span className="shrink-0 text-muted-foreground">
                      {tDashboard("gpu.moreDevices", { count: additionalSelectedUuidCount })}
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}
            {showNoGpu ? (
              <div className="flex items-center gap-1.5 border-t border-border/70 pt-2.5 text-xs text-muted-foreground">
                <HardDrive className="size-3" aria-hidden="true" />
                <span>{tDashboard("noGpuDetected")}</span>
              </div>
            ) : null}
          </div>
        </section>
      </CardRoot>
    </>
  );
}
