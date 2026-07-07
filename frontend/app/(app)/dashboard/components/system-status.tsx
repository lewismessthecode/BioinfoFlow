"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
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
import { gpuReadinessFactsFor } from "./readiness-helpers";

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

function labelForOptionalNote(tDashboard: DashboardTranslator, check: ReadinessCheck) {
  const key = readinessLabelKeys[check.id as keyof typeof readinessLabelKeys];
  return key ? tDashboard(key) : check.id;
}

function gpuOptionalNoteDescription(
  tDashboard: DashboardTranslator,
  check: ReadinessCheck,
) {
  const gpuFacts = gpuReadinessFactsFor(check);

  if (gpuFacts.state === "ready" || gpuFacts.state === "visible") {
    return tDashboard("systemNotes.gpuVisible", { count: gpuFacts.gpuCount, names: gpuFacts.names });
  }
  if (gpuFacts.state === "runtimeHidden") {
    return gpuFacts.recommendation
      ? tDashboard("systemNotes.gpuRuntimeHiddenWithRecommendation", { recommendation: gpuFacts.recommendation })
      : tDashboard("systemNotes.gpuRuntimeHidden");
  }
  if (gpuFacts.state === "hostOnly") {
    return gpuFacts.recommendation
      ? tDashboard("systemNotes.gpuHostOnlyWithRecommendation", { recommendation: gpuFacts.recommendation })
      : tDashboard("systemNotes.gpuHostOnly");
  }
  if (gpuFacts.state === "error") {
    return tDashboard("systemNotes.gpuError", { error: gpuFacts.error });
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

function actionHrefForOptionalNote(check: ReadinessCheck): string | null {
  return check.action?.kind === "route" ? (check.action.href ?? null) : null;
}

function actionLabelForOptionalNote(
  tDashboard: DashboardTranslator,
  check: ReadinessCheck,
): string | null {
  if (!check.action || !(check.id in readinessLabelKeys)) return null;
  return tDashboard(`readiness.checks.${check.id}.action`);
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
    <CardRoot variant="workbench" className="flex flex-1 flex-col">
      <CardHeader
        title={tDashboard("systemStatus")}
        className="border-b border-border/60"
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
      <CardContent className="space-y-0 p-0">
        <div className="grid divide-y divide-border/60 md:grid-cols-2 md:divide-x md:divide-y-0">
          <section className="px-4 py-3">
            <div className="flex items-center gap-2 text-foreground">
              <Container className="size-3.5 text-muted-foreground" />
              <span className="text-sm font-medium">{tDashboard("dockerAvailable")}</span>
            </div>
            <div className="mt-2 grid gap-1.5 pl-5 text-sm text-muted-foreground">
              <div className="flex items-center justify-between gap-3">
                <span>{tDashboard("docker.badgePrefix")}</span>
                <span className="flex items-center gap-1.5">
                  <span className={cn(
                    "size-1.5 rounded-full",
                    health?.docker.available ? "bg-muted-foreground/65" : "bg-destructive",
                  )} />
                  <span className={cn("text-xs", health?.docker.available ? "text-muted-foreground" : "text-destructive")}>
                    {health?.docker.available ? tDashboard("docker.available") : tDashboard("docker.notRunning")}
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>{tDashboard("docker.nvidiaRuntimePrefix")}</span>
                <span className="flex items-center gap-1.5">
                  <span className={cn(
                    "size-1.5 rounded-full",
                    health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime ? "bg-muted-foreground/65" : "bg-muted-foreground/35",
                  )} />
                  <span className="text-xs text-muted-foreground">
                    {health?.docker.nvidia_runtime || gpuInfo?.docker_nvidia_runtime
                      ? tDashboard("docker.available")
                      : tDashboard("docker.notFound")}
                  </span>
                </span>
              </div>
            </div>
          </section>

          <section className="px-4 py-3">
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
            <div className="mt-2 grid gap-1.5 pl-5 text-sm text-muted-foreground">
              {gpuRows.length > 0 ? (
                gpuRows.map((gpu) => (
                  <div key={gpu.index} className="flex items-center justify-between gap-3">
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

              {showRuntimeOnly ? (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
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
            </div>
          </section>
        </div>

        {optionalNotes.length > 0 ? (
          <section className="border-t border-border/60 bg-muted/15 px-4 py-3 text-xs leading-5 text-muted-foreground">
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
              {optionalNotes.map((note) => {
                const actionHref = actionHrefForOptionalNote(note);
                const actionLabel = actionLabelForOptionalNote(tDashboard, note);

                return (
                  <li key={`${note.id}-${note.status}`} className="flex gap-2">
                    <CircleAlert className="mt-1 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block font-medium text-foreground">
                        {labelForOptionalNote(tDashboard, note)}
                      </span>
                      <span>{descriptionForOptionalNote(tDashboard, note)}</span>
                      {actionHref && actionLabel ? (
                        <Link
                          href={actionHref}
                          className="mt-1 inline-flex items-center gap-1 font-medium text-foreground transition hover:text-primary"
                        >
                          {actionLabel}
                          <ArrowRight className="size-3" aria-hidden="true" />
                        </Link>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}
      </CardContent>
    </CardRoot>
  );
}
