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
import type { SystemHealth, GpuInfo, ReadinessCheck } from "./dashboard-types";

type SystemStatusProps = {
  health: SystemHealth | null;
  gpuInfo: GpuInfo | null;
  optionalNotes?: ReadinessCheck[];
};

type DashboardTranslator = ReturnType<typeof useTranslations>;

const readinessLabelKeys = {
  backend: "readiness.checks.backend.label",
  provider_key: "readiness.checks.provider_key.label",
  docker: "readiness.checks.docker.label",
  scheduler: "readiness.checks.scheduler.label",
  gpu: "readiness.checks.gpu.label",
  project: "readiness.checks.project.label",
  workflow_registry: "readiness.checks.workflow_registry.label",
  workflow_binding: "readiness.checks.workflow_binding.label",
} as const;

function readBoolean(value: unknown): boolean {
  return value === true;
}

function readNumber(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}

function labelForOptionalNote(tDashboard: DashboardTranslator, check: ReadinessCheck) {
  const key = readinessLabelKeys[check.id as keyof typeof readinessLabelKeys];
  return key ? tDashboard(key) : check.id;
}

function gpuOptionalNoteDescription(
  tDashboard: DashboardTranslator,
  check: ReadinessCheck,
) {
  const facts = check.facts ?? {};
  const gpuCount = readNumber(facts.gpu_count);
  const names = readStringList(facts.gpu_names).join(", ");
  const recommendation = readString(facts.recommendation);
  const error = readString(facts.error);

  if (readBoolean(facts.usable_for_gpu_workflows) || (readBoolean(facts.runtime_visible_to_backend) && gpuCount > 0)) {
    return tDashboard("systemNotes.gpuVisible", { count: gpuCount, names });
  }
  if (readBoolean(facts.docker_nvidia_runtime)) {
    return recommendation
      ? tDashboard("systemNotes.gpuRuntimeHiddenWithRecommendation", { recommendation })
      : tDashboard("systemNotes.gpuRuntimeHidden");
  }
  if (readBoolean(facts.nvidia_smi_found)) {
    return recommendation
      ? tDashboard("systemNotes.gpuHostOnlyWithRecommendation", { recommendation })
      : tDashboard("systemNotes.gpuHostOnly");
  }
  if (error && error !== "nvidia-smi not found") {
    return tDashboard("systemNotes.gpuError", { error });
  }
  return tDashboard("systemNotes.gpuCpuOnly");
}

function descriptionForOptionalNote(
  tDashboard: DashboardTranslator,
  check: ReadinessCheck,
) {
  if (check.id === "gpu") {
    return gpuOptionalNoteDescription(tDashboard, check);
  }
  return tDashboard("systemNotes.defaultDescription");
}

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

export function SystemStatus({ health, gpuInfo, optionalNotes = [] }: SystemStatusProps) {
  const tDashboard = useTranslations("dashboard");
  const gpuRows = gpuInfo?.gpus ?? [];
  const nvidiaSignal = hasNvidiaSignal(health, gpuInfo);
  const showNoGpu = !gpuInfo?.available && gpuRows.length === 0 && !nvidiaSignal;
  const showRuntimeOnly = !gpuInfo?.available && gpuRows.length === 0 && nvidiaSignal;
  const hasGpuOptionalNote = optionalNotes.some((note) => note.id === "gpu");

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

            {gpuInfo?.recommendation && !hasGpuOptionalNote ? (
              <p className="text-xs leading-5 text-muted-foreground">
                {gpuInfo.recommendation}
              </p>
            ) : null}

            {optionalNotes.length > 0 ? (
              <section className="rounded-xl border border-border/50 bg-muted/20 px-3 py-2 text-xs leading-5 text-muted-foreground">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium text-foreground">
                    {tDashboard("systemNotes.title")}
                  </p>
                  <span className="text-muted-foreground">
                    {tDashboard("systemNotes.badge")}
                  </span>
                </div>
                <p className="mt-1">{tDashboard("systemNotes.description")}</p>
                <ul className="mt-2 grid gap-2">
                  {optionalNotes.map((note) => (
                    <li key={`${note.id}-${note.status}`} className="flex gap-2">
                      <CircleAlert className="mt-1 size-3 shrink-0 text-warning" aria-hidden="true" />
                      <span className="min-w-0">
                        <span className="block font-medium text-foreground">
                          {labelForOptionalNote(tDashboard, note)}
                        </span>
                        <span>{descriptionForOptionalNote(tDashboard, note)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        </div>
      </CardContent>
    </CardRoot>
  );
}
