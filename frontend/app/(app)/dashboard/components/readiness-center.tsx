"use client";

import { useEffect } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2, CircleAlert, CircleDashed, CircleX, Rocket } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  CardContent,
  CardHeader,
  CardRoot,
} from "@/components/bioinfoflow/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  celebrateOnce,
  readinessMilestonesFromSummary,
} from "@/lib/celebrations";
import { cn } from "@/lib/utils";
import type { ReadinessCheck, ReadinessStatus } from "./dashboard-types";

type ReadinessCenterProps = {
  readiness: ReadinessStatus | null;
};

const statusIcon = {
  pass: CheckCircle2,
  warn: CircleAlert,
  fail: CircleX,
  skip: CircleDashed,
} as const;

const statusVariant = {
  pass: "success",
  warn: "warning",
  fail: "destructive",
  skip: "neutral",
} as const;

function SetupItem({ check }: { check: ReadinessCheck }) {
  const tDashboard = useTranslations("dashboard");
  const Icon = statusIcon[check.status];

  return (
    <div className="rounded-lg border border-border/60 bg-background/70 px-3 py-3">
      <div className="flex items-start gap-2.5">
        <Icon
          className={cn(
            "mt-0.5 h-4 w-4 shrink-0",
            check.status === "pass" && "text-success",
            check.status === "warn" && "text-warning",
            check.status === "fail" && "text-error",
            check.status === "skip" && "text-muted-foreground",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-foreground">{check.label}</p>
            <StatusBadge
              variant={statusVariant[check.status]}
              className="px-2 py-0.5 text-[10px]"
            >
              {tDashboard(`readiness.status.${check.status}`)}
            </StatusBadge>
          </div>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {check.hint || check.detail}
          </p>
        </div>
        {check.action_label && check.action_href ? (
          <Button asChild size="sm" variant="ghost" className="h-8 shrink-0 px-2">
            <Link href={check.action_href}>
              {check.action_label}
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function ReadinessCenter({ readiness }: ReadinessCenterProps) {
  const tDashboard = useTranslations("dashboard");

  useEffect(() => {
    for (const milestone of readinessMilestonesFromSummary(readiness?.summary)) {
      celebrateOnce(milestone);
    }
  }, [readiness?.summary]);

  if (!readiness || readiness.severity === "ready") return null;

  const total = readiness.checks.length;
  const completed = readiness.checks.filter((check) => check.status === "pass").length;
  const blockers = readiness.checks.filter(
    (check) => check.status === "fail" && check.severity === "blocking",
  );
  const optional = readiness.checks.filter(
    (check) => check.status !== "pass" && check.severity !== "blocking",
  );
  const progress = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <CardRoot variant="warning" className="mb-5">
      <CardHeader
        icon={Rocket}
        title={tDashboard("readiness.title")}
        badge={
          <StatusBadge variant="warning">
            {tDashboard("readiness.blockedBadge", { count: blockers.length })}
          </StatusBadge>
        }
        action={
          <Button asChild size="sm">
            <Link href={readiness.next_action.href}>{readiness.next_action.label}</Link>
          </Button>
        }
      />
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>{tDashboard("readiness.progress", { completed, total })}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-warning transition-[width]"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {blockers.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase text-muted-foreground">
              {tDashboard("readiness.blockers")}
            </h3>
            <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
              {blockers.map((check) => (
                <SetupItem key={check.id} check={check} />
              ))}
            </div>
          </div>
        ) : null}

        {optional.length > 0 ? (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase text-muted-foreground">
              {tDashboard("readiness.optional")}
            </h3>
            <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
              {optional.map((check) => (
                <SetupItem key={check.id} check={check} />
              ))}
            </div>
          </div>
        ) : null}

        <div className="rounded-lg bg-muted/35 px-3 py-2 text-xs leading-5 text-muted-foreground">
          {tDashboard("readiness.description", { warnings: optional.length })}
        </div>
      </CardContent>
    </CardRoot>
  );
}
