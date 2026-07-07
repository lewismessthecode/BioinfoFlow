"use client";

import { useTranslations } from "next-intl";
import {
  CheckCircle2,
  Container,
  Cpu,
  HardDrive,
} from "lucide-react";
import {
  CardRoot,
  CardContent,
  CardHeader,
} from "@/components/bioinfoflow/card";
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

function gpuSummaryVariant(health: SystemHealth | null, gpuInfo: GpuInfo | null) {
  if (gpuInfo?.parabricks_compatible) return "success";
  return "neutral";
}

export function SystemStatus({ health, gpuInfo }: SystemStatusProps) {
  const tDashboard = useTranslations("dashboard");
  const gpuRows = gpuInfo?.gpus ?? [];
  const nvidiaSignal = hasNvidiaSignal(health, gpuInfo);
  const showNoGpu = !gpuInfo?.available && gpuRows.length === 0 && !nvidiaSignal;

  return (
    <CardRoot variant="workbench" className="flex h-full flex-1 flex-col">
      <CardHeader
        title={tDashboard("systemStatus")}
        className="border-b-0 !pb-2"
        badge={
          <StatusBadge
            variant={health?.docker.available ? "neutral" : "destructive"}
          >
            {health?.docker.available
              ? tDashboard("healthy")
              : tDashboard("unavailable")}
          </StatusBadge>
        }
      />
      <CardContent className="!pt-0">
        <div className="grid gap-6 md:grid-cols-2">
          <section className="min-w-0">
            <div className="flex items-center gap-2 text-foreground">
              <Container className="size-3.5 text-muted-foreground" />
              <span className="text-sm font-medium">{tDashboard("dockerAvailable")}</span>
            </div>
            <dl className="mt-3 grid gap-2 text-sm text-muted-foreground">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                <dt className="truncate">{tDashboard("docker.badgePrefix")}</dt>
                <dd className="flex items-center gap-1.5">
                  <span className={cn(
                    "size-1.5 rounded-full",
                    health?.docker.available ? "bg-muted-foreground/65" : "bg-destructive",
                  )} />
                  <span className={cn("text-xs", health?.docker.available ? "text-muted-foreground" : "text-destructive")}>
                    {health?.docker.available ? tDashboard("docker.available") : tDashboard("docker.notRunning")}
                  </span>
                </dd>
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                <dt className="truncate">{tDashboard("docker.nvidiaRuntimePrefix")}</dt>
                <dd className="flex items-center gap-1.5">
                  <span className={cn(
                    "size-1.5 rounded-full",
                    health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime ? "bg-muted-foreground/65" : "bg-muted-foreground/35",
                  )} />
                  <span className="text-xs text-muted-foreground">
                    {health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime
                      ? tDashboard("docker.available")
                      : tDashboard("docker.notFound")}
                  </span>
                </dd>
              </div>
            </dl>
          </section>

          <section className="min-w-0">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-foreground">
                <Cpu className="size-3.5 text-muted-foreground" />
                <span className="text-sm font-medium">{tDashboard("gpuStatus")}</span>
              </div>
              {gpuInfo?.parabricks_compatible || nvidiaSignal ? (
                <StatusBadge variant={gpuSummaryVariant(health, gpuInfo)}>
                  {gpuInfo?.parabricks_compatible
                    ? tDashboard("parabricksCompatible")
                    : tDashboard("gpu.nvidiaRuntimeVisible")}
                </StatusBadge>
              ) : null}
            </div>
            <div className="mt-3 grid gap-2 text-sm text-muted-foreground">
              {gpuRows.length > 0 ? (
                gpuRows.map((gpu) => (
                  <div key={gpu.index} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3">
                    <span className="truncate">{gpu.name}</span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      <span className="size-1.5 rounded-full bg-muted-foreground/65" />
                      <span className="text-xs">{Math.round(gpu.memory_total_mb / 1024)}GB</span>
                    </span>
                  </div>
                ))
              ) : null}

              {gpuInfo?.parabricks_compatible ? (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <CheckCircle2 className="size-3" aria-hidden="true" />
                  <span>{tDashboard("parabricksCompatible")}</span>
                </div>
              ) : null}

              {showNoGpu ? (
                <div className="flex items-center gap-1.5 text-xs">
                  <HardDrive className="size-3" aria-hidden="true" />
                  <span>{tDashboard("noGpuDetected")}</span>
                </div>
              ) : null}

            </div>
          </section>
        </div>
      </CardContent>
    </CardRoot>
  );
}
