"use client";

import { useEffect, useRef, useState } from "react";
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
import { celebrateReadinessTransitions } from "@/lib/celebrations";
import { cn } from "@/lib/utils";
import type { ReadinessCheck, ReadinessStatus } from "./dashboard-types";

type ReadinessCenterProps = {
  readiness: ReadinessStatus | null;
  onRefresh?: () => Promise<void> | void;
};

type ReadinessCounts = {
  total: number;
  completed: number;
  blockers: number;
  optionalWarnings: number;
  progress: number;
};

const statusIcon = {
  pass: CheckCircle2,
  warn: CircleAlert,
  fail: CircleX,
  skip: CircleDashed,
} as const;

const statusVariant = {
  pass: "neutral",
  warn: "warning",
  fail: "destructive",
  skip: "neutral",
} as const;

function getCounts(checks: ReadinessCheck[]): ReadinessCounts {
  const total = checks.length;
  const completed = checks.filter((check) => check.status === "pass").length;
  const blockers = checks.filter(
    (check) => check.status === "fail" && check.severity === "blocking",
  ).length;
  const optionalWarnings = checks.filter(
    (check) => check.status !== "pass" && check.severity !== "blocking",
  ).length;

  return {
    total,
    completed,
    blockers,
    optionalWarnings,
    progress: total > 0 ? Math.round((completed / total) * 100) : 0,
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

function actionHrefFor(check: ReadinessCheck): string | null {
  if (check.id === "gpu") {
    return check.action_href ?? "/scheduler";
  }
  if (check.id === "workflow_binding") {
    return "/workflows?scope=hub";
  }
  return check.action_href ?? null;
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
  const actionLabel = check.action_label;
  const description = check.hint || check.detail;
  const rowLabel = isComplete
    ? tDashboard("readiness.completedLabel", { label: check.label })
    : `${check.label}: ${tDashboard(`readiness.status.${check.status}`)}`;

  return (
    <li
      aria-label={rowLabel}
      data-testid={`readiness-check-${check.id}`}
      className={cn(
        "rounded-xl border border-border/70 bg-card/70 px-3.5 py-3 transition-colors",
        "hover:border-border hover:bg-card",
        isComplete && "border-border/45 bg-muted/25 text-muted-foreground",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border",
            check.status === "pass" && "border-border bg-muted text-muted-foreground",
            check.status === "warn" && "border-warning-border bg-warning-muted text-warning",
            check.status === "fail" && "border-error-border bg-error-muted text-error",
            check.status === "skip" && "border-border bg-muted text-muted-foreground",
          )}
        >
          <Icon className="size-3.5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p
              className={cn(
                "text-sm font-semibold text-foreground",
                isComplete && "line-through text-muted-foreground decoration-muted-foreground/70",
              )}
            >
              {check.label}
            </p>
            <StatusBadge
              variant={statusVariant[check.status]}
              className="px-2 py-0.5 text-[10px]"
            >
              {tDashboard(`readiness.status.${check.status}`)}
            </StatusBadge>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {description}
          </p>
        </div>
        {!isComplete && actionLabel && check.id === "project" ? (
          <Button size="sm" variant="outline" className="h-8 shrink-0 px-2" onClick={onProjectAction}>
            {actionLabel}
            <ArrowRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        ) : null}
        {!isComplete && actionLabel && actionHref && check.id !== "project" ? (
          <Button asChild size="sm" variant="ghost" className="h-8 shrink-0 px-2">
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
      <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {title}
      </h3>
      <ul className="flex flex-col gap-2">
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
  const previousChecksRef = useRef<Array<Pick<ReadinessCheck, "id" | "status">> | null>(null);
  const [open, setOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    if (!readiness?.checks) return;

    celebrateReadinessTransitions(previousChecksRef.current, readiness.checks);
    previousChecksRef.current = readiness.checks.map((check) => ({
      id: check.id,
      status: check.status,
    }));
  }, [readiness?.checks]);

  if (!readiness) return null;

  const hasOpenChecks = readiness.checks.some((check) => check.status !== "pass");
  if (!hasOpenChecks && readiness.severity === "ready") return null;

  const counts = getCounts(readiness.checks);
  const groups = groupChecks(readiness.checks);
  const tone = counts.blockers > 0 ? "warning" : "default";

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
      <CardRoot variant={tone} className="mb-5 bg-card/80 backdrop-blur">
        <CardContent className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            aria-label={tDashboard("readiness.trigger")}
            className="group flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-muted/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            onClick={() => setOpen(true)}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl border border-warning-border bg-warning-muted text-warning">
              <Rocket className="size-4" aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">
                  {tDashboard("readiness.title")}
                </span>
                <StatusBadge variant={counts.blockers > 0 ? "warning" : "neutral"}>
                  {tDashboard("readiness.triggerSummary", {
                    completed: counts.completed,
                    total: counts.total,
                  })}
                </StatusBadge>
              </span>
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                {counts.blockers > 0
                  ? tDashboard("readiness.requiredRemaining", { count: counts.blockers })
                  : tDashboard("readiness.optionalWarnings", { count: counts.optionalWarnings })}
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
        className="flex w-[min(520px,92vw)] flex-col gap-0 overflow-hidden sm:max-w-none"
      >
        <SheetHeader className="border-b border-border/70 p-5 pr-12">
          <div className="flex items-center gap-3">
            <span className="flex size-10 items-center justify-center rounded-2xl border border-border bg-muted text-muted-foreground">
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

        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto bg-background/95 p-5">
          <div className="flex flex-col gap-2 rounded-2xl border border-border/70 bg-muted/25 p-3">
            <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>{tDashboard("readiness.progress", { completed: counts.completed, total: counts.total })}</span>
              <span>{counts.progress}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full transition-[width] duration-300",
                  counts.blockers > 0 ? "bg-warning" : "bg-success",
                )}
                style={{ width: `${counts.progress}%` }}
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

        <div className="flex items-center justify-between gap-3 border-t border-border/70 p-4">
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
