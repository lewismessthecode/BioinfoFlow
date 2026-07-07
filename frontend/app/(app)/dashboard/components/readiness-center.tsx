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
} from "lucide-react";
import { useTranslations } from "next-intl";
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
import {
  gpuReadinessFactsFor,
  readBoolean,
  readNumber,
  summarizeReadinessChecks,
} from "./readiness-helpers";

type ReadinessCenterProps = {
  readiness: ReadinessStatus | null;
  onRefresh?: () => Promise<void> | void;
};

const statusIcon = {
  pass: CheckCircle2,
  warn: CircleAlert,
  fail: CircleX,
  skip: CircleDashed,
} as const;

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
      const gpuFacts = gpuReadinessFactsFor(check);

      if (gpuFacts.state === "ready") {
        return tDashboard("readiness.checks.gpu.detail.ready", {
          count: gpuFacts.gpuCount,
          names: gpuFacts.names,
        });
      }
      if (gpuFacts.state === "visible") {
        return tDashboard("readiness.checks.gpu.detail.visible", {
          count: gpuFacts.gpuCount,
          names: gpuFacts.names,
        });
      }
      if (gpuFacts.state === "runtimeHidden") {
        return tDashboard("readiness.checks.gpu.detail.runtimeHidden", {
          recommendation: gpuFacts.recommendation,
        });
      }
      if (gpuFacts.state === "hostOnly") {
        return tDashboard("readiness.checks.gpu.detail.hostOnly", {
          recommendation: gpuFacts.recommendation,
        });
      }
      if (gpuFacts.state === "error") {
        return tDashboard("readiness.checks.gpu.detail.error", { error: gpuFacts.error });
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
        "group rounded-lg px-2.5 transition-colors",
        "hover:bg-muted/35",
        isComplete ? "py-1.5 text-muted-foreground" : "py-2.5",
        isComplete && "text-muted-foreground",
      )}
    >
      <div className={cn("flex gap-3", isComplete ? "items-center" : "items-start")}>
        <span
          className={cn(
            "flex shrink-0 items-center justify-center rounded-full border",
            isComplete ? "size-4" : "mt-0.5 size-5",
            check.status === "pass" && "border-border bg-muted text-muted-foreground",
            check.status === "warn" && "border-warning-border bg-warning-muted text-warning",
            check.status === "fail" && "border-warning-border bg-warning-muted text-warning",
            check.status === "skip" && "border-border bg-muted text-muted-foreground",
          )}
        >
          <Icon className={cn(isComplete ? "size-3" : "size-3.5")} aria-hidden="true" />
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
          {!isComplete ? (
            <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
        {!isComplete && actionLabel && check.action?.kind === "dialog" ? (
          <Button size="sm" variant="ghost" className="h-8 shrink-0 rounded-md px-2.5 text-xs" onClick={onProjectAction}>
            {actionLabel}
            <ArrowRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        ) : null}
        {!isComplete && actionLabel && actionHref && check.id !== "project" ? (
          <Button asChild size="sm" variant="ghost" className="h-8 shrink-0 rounded-md px-2.5 text-xs">
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
  description,
  checks,
  onProjectAction,
}: {
  title: string;
  description?: string;
  checks: ReadinessCheck[];
  onProjectAction: () => void;
}) {
  if (checks.length === 0) return null;

  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="flex items-center justify-between px-1 text-xs font-medium text-muted-foreground">
        <span>{title}</span>
        <span>{checks.length}</span>
      </h3>
      {description ? (
        <p className="px-1 text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      ) : null}
      <ul className="grid gap-1 rounded-lg bg-card/45 p-1">
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

  const readinessSummary = summarizeReadinessChecks(readiness.checks);
  const { groups } = readinessSummary;
  if (!readinessSummary.hasBlockingOpenChecks) return null;

  const requiredRemaining = readinessSummary.requiredTotal - readinessSummary.requiredCompleted;
  const triggerSummary = tDashboard("readiness.triggerSummary", {
    completed: readinessSummary.requiredCompleted,
    total: readinessSummary.requiredTotal,
  });
  const requiredRemainingLabel = tDashboard("readiness.requiredRemaining", { count: requiredRemaining });
  const optionalWarningsLabel = readinessSummary.optionalWarnings > 0
    ? tDashboard("readiness.optionalWarnings", { count: readinessSummary.optionalWarnings })
    : null;
  const triggerAriaLabel = [
    tDashboard("readiness.trigger"),
    triggerSummary,
    requiredRemainingLabel,
    optionalWarningsLabel,
  ].filter(Boolean).join(", ");

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
      <button
        type="button"
        aria-label={triggerAriaLabel}
        className="group flex min-w-0 w-full items-center gap-3 rounded-lg border border-border/70 bg-muted/20 px-3 py-2.5 text-left transition-colors hover:border-foreground/15 hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2"
        data-testid="readiness-compact-strip"
        onClick={() => setOpen(true)}
      >
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background text-muted-foreground">
          <ListChecks className="size-4" aria-hidden="true" />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:items-center">
          <span className="min-w-0 truncate text-sm font-medium text-foreground">
            {tDashboard("readiness.title")}
          </span>
          <span className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <StatusBadge variant="neutral">
              {triggerSummary}
            </StatusBadge>
            <span className="truncate">{requiredRemainingLabel}</span>
            {optionalWarningsLabel ? (
              <span className="truncate text-muted-foreground/80">
                {optionalWarningsLabel}
              </span>
            ) : null}
          </span>
        </span>
        <ArrowRight
          className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </button>

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
          <div className="px-1">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm font-medium text-foreground">
                {tDashboard("readiness.progress", { completed: readinessSummary.requiredCompleted, total: readinessSummary.requiredTotal })}
              </p>
              <span className="text-xs font-medium text-muted-foreground">{readinessSummary.requiredProgress}%</span>
            </div>
            <div className="mt-3 h-1 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-foreground/70 transition-[width] duration-300"
                style={{ width: `${readinessSummary.requiredProgress}%` }}
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
            description={tDashboard("readiness.optionalDescription")}
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
            {optionalWarningsLabel ?? tDashboard("readiness.requiredRemaining", { count: requiredRemaining })}
          </p>
          {onRefresh ? (
            <Button
              size="sm"
              variant="outline"
              disabled={isRefreshing}
              aria-busy={isRefreshing}
              onClick={() => void handleRefresh()}
            >
              <RefreshCw data-icon="inline-start" aria-hidden="true" />
              {isRefreshing ? tDashboard("readiness.refreshing") : tDashboard("readiness.refresh")}
            </Button>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
