"use client";

import { useTranslations } from "next-intl";
import {
  CheckCircle2,
  CircleAlert,
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
  if (gpuInfo?.available || hasNvidiaSignal(health, gpuInfo)) return "warning";
  return "neutral";
}

export function SystemStatus({ health, gpuInfo }: SystemStatusProps) {
  const tDashboard = useTranslations("dashboard");
  const gpuRows = gpuInfo?.gpus ?? [];
  const nvidiaSignal = hasNvidiaSignal(health, gpuInfo);
  const showNoGpu = !gpuInfo?.available && gpuRows.length === 0 && !nvidiaSignal;
  const showRuntimeOnly = !gpuInfo?.available && gpuRows.length === 0 && nvidiaSignal;

  return (
    <CardRoot className="mb-5 flex flex-1 flex-col">
      <CardHeader
        title={tDashboard("systemStatus")}
        badge={
          <StatusBadge
            variant={health?.docker.available ? "success" : "destructive"}
          >
            {health?.docker.available
              ? tDashboard("healthy")
              : tDashboard("unavailable")}
          </StatusBadge>
        }
      />
      <CardContent className="flex flex-col gap-6 md:grid md:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Container className="size-4 text-muted-foreground" />
            <span className="text-sm font-medium">{tDashboard("dockerAvailable")}</span>
          </div>
          <div className="flex flex-col gap-2 pl-6 text-sm text-muted-foreground">
            <div className="flex items-center justify-between gap-3">
              <span>{tDashboard("docker.badgePrefix")}</span>
              <span className="flex items-center gap-1.5">
                <span className={cn(
                  "size-1.5 rounded-full",
                  health?.docker.available ? "bg-success" : "bg-destructive",
                )} />
                <span className={cn("text-xs", health?.docker.available ? "text-success" : "text-destructive")}>
                  {health?.docker.available ? tDashboard("docker.available") : tDashboard("docker.notRunning")}
                </span>
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span>{tDashboard("docker.nvidiaRuntimePrefix")}</span>
              <span className="flex items-center gap-1.5">
                <span className={cn(
                  "size-1.5 rounded-full",
                  health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime ? "bg-success" : "bg-muted-foreground/50",
                )} />
                <span className="text-xs text-muted-foreground">
                  {health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime
                    ? tDashboard("docker.available")
                    : tDashboard("docker.notFound")}
                </span>
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Cpu className="size-4 text-muted-foreground" />
              <span className="text-sm font-medium">{tDashboard("gpuStatus")}</span>
            </div>
            <StatusBadge variant={gpuSummaryVariant(health, gpuInfo)}>
              {gpuInfo?.parabricks_compatible
                ? tDashboard("parabricksCompatible")
                : nvidiaSignal
                  ? tDashboard("gpu.nvidiaRuntimeVisible")
                  : tDashboard("gpuStatus")}
            </StatusBadge>
          </div>
          <div className="flex flex-col gap-2 pl-6 text-sm text-muted-foreground">
            {gpuRows.length > 0 ? (
              gpuRows.map((gpu) => (
                <div key={gpu.index} className="flex items-center justify-between gap-3">
                  <span className="truncate">{gpu.name}</span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    <span className={cn(
                      "size-1.5 rounded-full",
                      gpu.gpu_type === "Apple Silicon" ? "bg-info" : "bg-success",
                    )} />
                    <span className="text-xs">{Math.round(gpu.memory_total_mb / 1024)}GB</span>
                  </span>
                </div>
              ))
            ) : null}

            {gpuInfo?.parabricks_compatible ? (
              <div className="flex items-center gap-1.5 text-xs text-info">
                <CheckCircle2 className="size-3" aria-hidden="true" />
                <span>{tDashboard("parabricksCompatible")}</span>
              </div>
            ) : null}

            {showRuntimeOnly ? (
              <div className="flex items-center gap-1.5 text-xs text-warning">
                <CircleAlert className="size-3" aria-hidden="true" />
                <span>{tDashboard("gpu.detailsUnavailable")}</span>
              </div>
            ) : null}

            {showNoGpu ? (
              <div className="flex items-center gap-1.5 text-xs">
                <HardDrive className="size-3" aria-hidden="true" />
                <span>{tDashboard("noGpuDetected")}</span>
              </div>
            ) : null}

            {gpuInfo?.recommendation ? (
              <p className="text-xs leading-5 text-muted-foreground">
                {gpuInfo.recommendation}
              </p>
            ) : null}
          </div>
        </div>
      </CardContent>
    </CardRoot>
  );
}
