"use client";

import Link from "next/link";
import { CheckCircle2, CircleAlert, CircleDashed, CircleX, Rocket } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  CardContent,
  CardHeader,
  CardRoot,
} from "@/components/bioinfoflow/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
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

function visibleChecks(checks: ReadinessCheck[]) {
  const actionable = checks.filter((check) => check.status !== "pass");
  return actionable.length > 0 ? actionable.slice(0, 4) : checks.slice(0, 4);
}

export function ReadinessCenter({ readiness }: ReadinessCenterProps) {
  const tDashboard = useTranslations("dashboard");

  if (!readiness || readiness.severity === "ready") return null;

  const failed = readiness.checks.filter((check) => check.status === "fail").length;
  const warnings = readiness.checks.filter((check) => check.status === "warn").length;

  return (
    <CardRoot variant="warning" className="mb-5">
      <CardHeader
        icon={Rocket}
        title={tDashboard("readiness.title")}
        badge={
          <StatusBadge variant="warning">
            {tDashboard("readiness.blockedBadge", { count: failed })}
          </StatusBadge>
        }
        action={
          <Button asChild size="sm">
            <Link href={readiness.next_action.href}>{readiness.next_action.label}</Link>
          </Button>
        }
      />
      <CardContent className="space-y-4">
        <p className="text-sm leading-6 text-muted-foreground">
          {tDashboard("readiness.description", { warnings })}
        </p>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {visibleChecks(readiness.checks).map((check) => {
            const Icon = statusIcon[check.status];
            return (
              <div
                key={check.id}
                className="rounded-lg border border-border/60 bg-muted/20 px-3 py-2.5"
              >
                <div className="flex items-start gap-2">
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
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium text-foreground">
                        {check.label}
                      </p>
                      <StatusBadge
                        variant={statusVariant[check.status]}
                        className="shrink-0 px-2 py-0.5 text-[10px]"
                      >
                        {tDashboard(`readiness.status.${check.status}`)}
                      </StatusBadge>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      {check.hint || check.detail}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </CardRoot>
  );
}
