"use client";

import { useTranslations } from "next-intl";
import {
  Container,
  Cpu,
  HardDrive,
  CheckCircle2,
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

export function SystemStatus({ health, gpuInfo }: SystemStatusProps) {
  const tDashboard = useTranslations("dashboard");

  return (
    <CardRoot className="mb-5 flex-1 flex flex-col">
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
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Docker Status */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Container className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">{tDashboard("dockerAvailable")}</span>
            </div>
            <div className="pl-6 space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center justify-between">
                <span>{tDashboard("docker.badgePrefix")}</span>
                <span className="flex items-center gap-1.5">
                  <span className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    health?.docker.available ? "bg-success" : "bg-destructive"
                  )} />
                  <span className={cn("text-xs", health?.docker.available ? "text-success" : "text-destructive")}>
                    {health?.docker.available ? tDashboard("docker.available") : tDashboard("docker.notRunning")}
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>{tDashboard("docker.nvidiaRuntimePrefix")}</span>
                <span className="flex items-center gap-1.5">
                  <span className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    health?.docker.nvidia_runtime ? "bg-success" : "bg-muted-foreground/50"
                  )} />
                  <span className="text-xs text-muted-foreground">
                    {health?.docker.nvidia_runtime ? tDashboard("docker.available") : tDashboard("docker.notFound")}
                  </span>
                </span>
              </div>
            </div>
          </div>

          {/* GPU Status */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">{tDashboard("gpuStatus")}</span>
            </div>
            <div className="pl-6 space-y-2 text-sm text-muted-foreground">
              {gpuInfo?.available && gpuInfo.gpus.length > 0 ? (
                <>
                  {gpuInfo.gpus.map((gpu) => (
                    <div key={gpu.index} className="flex items-center justify-between">
                      <span className="truncate mr-2">{gpu.name}</span>
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          gpu.gpu_type === "Apple Silicon" ? "bg-info" : "bg-success"
                        )} />
                        <span className="text-xs">{Math.round(gpu.memory_total_mb / 1024)}GB</span>
                      </span>
                    </div>
                  ))}
                  {gpuInfo.parabricks_compatible && (
                    <div className="flex items-center gap-1.5 text-xs text-info">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>{tDashboard("parabricksCompatible")}</span>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex items-center gap-1.5 text-xs">
                  <HardDrive className="h-3 w-3" />
                  <span>{tDashboard("noGpuDetected")}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </CardRoot>
  );
}
