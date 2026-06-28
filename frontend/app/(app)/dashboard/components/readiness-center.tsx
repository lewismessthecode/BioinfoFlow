"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  CircleX,
  ListChecks,
  RefreshCw,
  Rocket,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { CardContent, CardRoot } from "@/components/bioinfoflow/card";
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";
import type { ReadinessCheck, ReadinessStatus } from "./dashboard-types";

type ReadinessCenterProps = {
  readiness: ReadinessStatus | null;
  onRefresh?: () => Promise<void> | void;
};

type ReadinessCounts = {
  requiredTotal: number;
  requiredCompleted: number;
  blockers: number;
  optionalWarnings: number;
  requiredProgress: number;
};

const statusIcon = {
  pass: CheckCircle2,
  warn: CircleAlert,
  fail: CircleX,
  skip: CircleDashed,
} as const;

function getCounts(checks: ReadinessCheck[]): ReadinessCounts {
  const requiredChecks = checks.filter((check) => check.severity === "blocking");
  const requiredTotal = requiredChecks.length;
  const requiredCompleted = requiredChecks.filter(
    (check) => check.status === "pass",
  ).length;
  const blockers = checks.filter(
    (check) => check.status === "fail" && check.severity === "blocking",
  ).length;
  const optionalWarnings = checks.filter(
    (check) => check.status !== "pass" && check.severity !== "blocking",
  ).length;

  return {
    requiredTotal,
    requiredCompleted,
    blockers,
    optionalWarnings,
    requiredProgress:
      requiredTotal > 0 ? Math.round((requiredCompleted / requiredTotal) * 100) : 0,
  };
}

function groupChecks(checks: ReadinessCheck[]) {
  return {
    required: checks.filter(
      (check) => check.status !== "pass" && check.severity === "blocking",
    ),
    optional: checks.filter(
      (check) => check.status !== "pass" && check.severity !== "blocking",
    ),
    completed: checks.filter((check) => check.status === "pass"),
  };
}

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

function labelForCheck(
  tDashboard: ReturnType<typeof useTranslations>,
  check: ReadinessCheck,
) {
  return tDashboard(`readiness.checks.${check.id}.label`);
}

function descriptionForCheck(
  tDashboard: ReturnType<typeof useTranslations>,
  check: ReadinessCheck,
) {
  const facts = check.facts ?? {};

  switch (check.id) {
    case "backend":
      return tDashboard("readiness.checks.backend.detail.pass");
    case "provider_key":
      return tDashboard(
        `readiness.checks.provider_key.detail.${readBoolean(facts.configured) ? "pass" : "fail"}`,
      );
    case "docker":
      return tDashboard(
        `readiness.checks.docker.detail.${readBoolean(facts.available) ? "pass" : "fail"}`,
      );
    case "scheduler":
      return tDashboard(
        `readiness.checks.scheduler.detail.${readBoolean(facts.available) ? "pass" : "fail"}`,
      );
    case "project":
      return readNumber(facts.count) > 0
        ? tDashboard("readiness.checks.project.detail.pass", { count: readNumber(facts.count) })
        : tDashboard("readiness.checks.project.detail.fail");
    case "workflow_registry":
      return readNumber(facts.count) > 0
        ? tDashboard("readiness.checks.workflow_registry.detail.pass", {
            count: readNumber(facts.count),
          })
        : tDashboard("readiness.checks.workflow_registry.detail.fail");
    case "workflow_binding":
      return readNumber(facts.count) > 0
        ? tDashboard("readiness.checks.workflow_binding.detail.pass", {
            count: readNumber(facts.count),
          })
        : tDashboard("readiness.checks.workflow_binding.detail.fail");
    case "gpu": {
      const gpuCount = readNumber(facts.gpu_count);
      const names = readStringList(facts.gpu_names).join(", ");
      const recommendation = readString(facts.recommendation);
      const error = readString(facts.error);

      if (readBoolean(facts.usable_for_gpu_workflows)) {
        return tDashboard("readiness.checks.gpu.detail.ready", {
          count: gpuCount,
          names,
        });
      }
      if (readBoolean(facts.runtime_visible_to_backend) && gpuCount > 0) {
        return tDashboard("readiness.checks.gpu.detail.visible", {
          count: gpuCount,
          names,
        });
      }
      if (readBoolean(facts.docker_nvidia_runtime)) {
        return tDashboard("readiness.checks.gpu.detail.runtimeHidden", {
          recommendation,
        });
      }
      if (readBoolean(facts.nvidia_smi_found)) {
        return tDashboard("readiness.checks.gpu.detail.hostOnly", {
          recommendation,
        });
      }
      if (error && error !== "nvidia-smi not found") {
        return tDashboard("readiness.checks.gpu.detail.error", { error });
      }
      return tDashboard("readiness.checks.gpu.detail.cpuOnly");
    }
    default:
      return "";
  }
}

function actionHrefFor(check: ReadinessCheck): string | null {
  if (check.id === "workflow_binding") {
    return "/workflows?scope=hub";
  }
  return check.action?.kind === "route" ? (check.action.href ?? null) : null;
}

function actionLabelForCheck(
  tDashboard: ReturnType<typeof useTranslations>,
  check: ReadinessCheck,
) {
  if (!check.action) return null;
  return tDashboard(`readiness.checks.${check.id}.action`);
}

function SetupItem({
  check,
  onProjectAction,
}: {
  check: ReadinessCheck;
  onProjectAction: () => void;
}) {
  const tDashboard = useTranslations("dashboard");
  const Icon = statusIcon[check.status];
  const isComplete = check.status === "pass";
  const actionHref = actionHrefFor(check);
  const actionLabel = actionLabelForCheck(tDashboard, check);
  const description = descriptionForCheck(tDashboard, check);
  const label = labelForCheck(tDashboard, check);
  const statusText = tDashboard(`readiness.status.${check.status}`);
  const rowLabel = isComplete
    ? tDashboard("readiness.completedLabel", { label })
    : `${label}: ${statusText}`;

  return (
    <li
      aria-label={rowLabel}
      data-testid={`readiness-check-${check.id}`}
      className={cn(
        "group rounded-2xl px-2.5 py-2.5 transition-colors",
        "hover:bg-muted/35",
        check.status === "fail" && "bg-warning-muted/30",
        check.status === "warn" && "bg-warning-muted/20",
        isComplete && "text-muted-foreground",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border",
            check.status === "pass" && "border-border bg-muted text-muted-foreground",
            check.status === "warn" && "border-warning-border bg-warning-muted text-warning",
            check.status === "fail" && "border-warning-border bg-warning-muted text-warning",
            check.status === "skip" && "border-border bg-muted text-muted-foreground",
          )}
        >
          <Icon className="size-3.5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <p
              className={cn(
                "text-sm font-medium text-foreground",
                isComplete && "line-through text-muted-foreground decoration-muted-foreground/70",
              )}
            >
              {label}
            </p>
            {!isComplete ? (
              <span
                className={cn(
                  "text-xs font-medium",
                  check.status === "fail" && "text-warning",
                  check.status === "warn" && "text-warning",
                  check.status === "skip" && "text-muted-foreground",
                )}
              >
                {statusText}
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
            {description}
          </p>
        </div>
        {!isComplete && actionLabel && check.action?.kind === "dialog" ? (
          <Button size="sm" variant="ghost" className="h-8 shrink-0 rounded-full px-2.5 text-xs" onClick={onProjectAction}>
            {actionLabel}
            <ArrowRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        ) : null}
        {!isComplete && actionLabel && actionHref && check.id !== "project" ? (
          <Button asChild size="sm" variant="ghost" className="h-8 shrink-0 rounded-full px-2.5 text-xs">
            <Link href={actionHref}>
              {actionLabel}
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function ChecklistSection({
  title,
  checks,
  onProjectAction,
}: {
  title: string;
  checks: ReadinessCheck[];
  onProjectAction: () => void;
}) {
  if (checks.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center justify-between px-1 text-xs font-medium text-muted-foreground">
        <span>{title}</span>
        <span>{checks.length}</span>
      </h3>
      <ul className="divide-y divide-border/50 rounded-[22px] border border-border/60 bg-card/75 p-1 shadow-sm shadow-foreground/5">
        {checks.map((check) => (
          <SetupItem key={check.id} check={check} onProjectAction={onProjectAction} />
        ))}
      </ul>
    </section>
  );
}

export function ReadinessCenter({ readiness, onRefresh }: ReadinessCenterProps) {
  const tDashboard = useTranslations("dashboard");
  const workspaceShell = useOptionalWorkspaceShell();
  const [open, setOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  if (!readiness) return null;

  const counts = getCounts(readiness.checks);
  const groups = groupChecks(readiness.checks);
  const hasBlockingOpenChecks = readiness.checks.some(
    (check) => check.status !== "pass" && check.severity === "blocking",
  );
  if (!hasBlockingOpenChecks) return null;

  const requiredRemaining = counts.requiredTotal - counts.requiredCompleted;

  const handleRefresh = async () => {
    if (!onRefresh) return;
    setIsRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleProjectAction = () => {
    workspaceShell?.openCreateProjectDialog();
    setOpen(false);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <CardRoot
        variant="warning"
        className="mb-5 overflow-hidden border border-border/70 bg-card/85 shadow-sm shadow-foreground/5"
      >
        <CardContent className="p-2">
          <button
            type="button"
            aria-label={tDashboard("readiness.trigger")}
            className="group flex min-w-0 w-full items-center gap-3 rounded-[22px] px-3 py-3 text-left transition-colors hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            onClick={() => setOpen(true)}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl border border-warning-border/70 bg-warning-muted text-warning">
              <Rocket className="size-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">
                  {tDashboard("readiness.title")}
                </span>
                <StatusBadge variant="warning">
                  {tDashboard("readiness.triggerSummary", {
                    completed: counts.requiredCompleted,
                    total: counts.requiredTotal,
                  })}
                </StatusBadge>
                {counts.optionalWarnings > 0 ? (
                  <StatusBadge variant="neutral">
                    {tDashboard("readiness.optionalWarnings", {
                      count: counts.optionalWarnings,
                    })}
                  </StatusBadge>
                ) : null}
              </span>
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                {tDashboard("readiness.requiredRemaining", { count: requiredRemaining })}
              </span>
            </span>
            <ArrowRight
              className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
              aria-hidden="true"
            />
          </button>
        </CardContent>
      </CardRoot>

      <SheetContent
        side="right"
        className="flex w-[min(520px,92vw)] flex-col gap-0 overflow-hidden border-l border-border/70 bg-background/98 shadow-[-24px_0_60px_rgba(15,23,42,0.12)] sm:max-w-none"
      >
        <SheetHeader className="border-b border-border/70 p-5 pr-12">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-2xl border border-border bg-muted/70 text-muted-foreground">
              <ListChecks className="size-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <SheetTitle>{tDashboard("readiness.drawerTitle")}</SheetTitle>
              <SheetDescription>
                {tDashboard("readiness.drawerDescription")}
              </SheetDescription>
            </div>
          </div>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto bg-background/95 p-4">
          <div className="rounded-[22px] border border-border/60 bg-card/75 p-4 shadow-sm shadow-foreground/5">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm font-medium text-foreground">
                {tDashboard("readiness.progress", { completed: counts.requiredCompleted, total: counts.requiredTotal })}
              </p>
              <span className="text-xs font-medium text-muted-foreground">{counts.requiredProgress}%</span>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-warning transition-[width] duration-300"
                style={{ width: `${counts.requiredProgress}%` }}
              />
            </div>
          </div>

          <ChecklistSection
            title={tDashboard("readiness.blockers")}
            checks={groups.required}
            onProjectAction={handleProjectAction}
          />
          <ChecklistSection
            title={tDashboard("readiness.optional")}
            checks={groups.optional}
            onProjectAction={handleProjectAction}
          />
          <ChecklistSection
            title={tDashboard("readiness.completed")}
            checks={groups.completed}
            onProjectAction={handleProjectAction}
          />
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border/70 bg-background/96 p-4">
          <p className="text-xs leading-5 text-muted-foreground">
            {tDashboard("readiness.description", { warnings: counts.optionalWarnings })}
          </p>
          {onRefresh ? (
            <Button size="sm" variant="outline" disabled={isRefreshing} onClick={() => void handleRefresh()}>
              <RefreshCw data-icon="inline-start" aria-hidden="true" />
              {tDashboard("readiness.refresh")}
            </Button>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
