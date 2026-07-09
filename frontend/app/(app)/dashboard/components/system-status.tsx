"use client";

import { useTranslations } from "next-intl";
import {
  CheckCircle2,
  Container,
  Cpu,
  HardDrive,
} from "@/lib/icons";
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
        <div className="grid gap-5 md:grid-cols-2">
          <section className="min-w-0">
            <div className="flex items-center gap-2 text-foreground">
              <Container className="size-3.5 text-muted-foreground/80" />
              <span className="text-sm font-medium">{tDashboard("dockerAvailable")}</span>
            </div>
            <dl className="mt-3 grid gap-2.5 text-sm">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2.5">
                <dt className="truncate text-muted-foreground">{tDashboard("docker.badgePrefix")}</dt>
                <dd className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className={cn(
                    "size-1.5 rounded-full",
                    health?.docker.available ? "bg-muted-foreground/60" : "bg-destructive",
                  )} />
                  {health?.docker.available ? tDashboard("docker.available") : tDashboard("docker.notRunning")}
                </dd>
              </div>
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2.5">
                <dt className="truncate text-muted-foreground">{tDashboard("docker.nvidiaRuntimePrefix")}</dt>
                <dd className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className={cn(
                    "size-1.5 rounded-full",
                    health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime ? "bg-muted-foreground/60" : "bg-muted-foreground/30",
                  )} />
                  {health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime
                    ? tDashboard("docker.available")
                    : tDashboard("docker.notFound")}
                </dd>
              </div>
            </dl>
          </section>

          <section className="min-w-0">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-foreground">
                <Cpu className="size-3.5 text-muted-foreground/80" />
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
            <div className="mt-3 grid gap-2.5 text-sm">
              {gpuRows.map((gpu) => (
                <div key={gpu.index} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border/70 pt-2.5">
                  <span className="truncate text-muted-foreground">{gpu.name}</span>
                  <span className="font-mono text-xs text-foreground tabular-nums">
                    {Math.round(gpu.memory_total_mb / 1024)}GB
                  </span>
                </div>
              ))}

              {gpuInfo?.parabricks_compatible ? (
                <div className="flex items-center gap-1.5 border-t border-border/70 pt-2.5 text-xs text-muted-foreground">
                  <CheckCircle2 className="size-3" aria-hidden="true" />
                  <span>{tDashboard("parabricksCompatible")}</span>
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
        </div>
      </CardContent>
    </CardRoot>
  );
}
