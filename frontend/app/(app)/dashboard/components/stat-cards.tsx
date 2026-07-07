"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Play, GitBranch, Container, FolderOpen } from "lucide-react";
import {
  CardRoot,
  CardContent,
} from "@/components/bioinfoflow/card";
import type { DashboardStats } from "./dashboard-types";

type StatCardsProps = {
  stats: DashboardStats | null;
};

export function StatCards({ stats }: StatCardsProps) {
  const tDashboard = useTranslations("dashboard");
  const tStatus = useTranslations("status");

  const statCards = [
    {
      key: "runs",
      icon: Play,
      href: "/runs?scope=all",
      getValue: () => stats?.runs.total ?? 0,
      getDetails: () => [
        { label: tStatus("completed"), value: stats?.runs.completed ?? 0 },
        { label: tStatus("running"), value: stats?.runs.running ?? 0 },
        { label: tStatus("failed"), value: stats?.runs.failed ?? 0 },
      ],
    },
    {
      key: "workflows",
      icon: GitBranch,
      href: "/workflows?scope=hub",
      getValue: () => stats?.workflows.total ?? 0,
      getDetails: () => [
        { label: tDashboard("registered"), value: stats?.workflows.total ?? 0 },
      ],
    },
    {
      key: "images",
      icon: Container,
      href: "/images",
      getValue: () => stats?.images.total ?? 0,
      getDetails: () => [
        { label: tDashboard("local"), value: stats?.images.local ?? 0 },
        { label: tDashboard("remote"), value: stats?.images.remote ?? 0 },
      ],
    },
    {
      key: "projects",
      icon: FolderOpen,
      href: "/agent",
      getValue: () => stats?.projects.total ?? 0,
      getDetails: () => [
        { label: tDashboard("active"), value: stats?.projects.total ?? 0 },
      ],
    },
  ];

  return (
    <div
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
      data-testid="dashboard-metric-grid"
    >
      {statCards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.key}
            className="min-w-0"
          >
            <CardRoot variant="workbench" className="h-full">
              <Link
                href={card.href}
                className="group block h-full rounded-[inherit] transition-colors hover:bg-muted/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-inset"
              >
                <CardContent className="flex min-h-[7rem] flex-col justify-between gap-4 !p-5">
                  <span className="flex items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-muted-foreground transition-colors group-hover:text-foreground">
                        {tDashboard(card.key)}
                      </span>
                      <span className="mt-2 block font-mono text-3xl font-semibold tracking-tight text-foreground tabular-nums">
                        {card.getValue()}
                      </span>
                      {card.key === "runs" && (stats?.runs.running ?? 0) > 0 ? (
                        <span className="mt-2 flex items-center gap-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-info animate-pulse motion-reduce:animate-none" />
                          <span className="text-xs font-medium text-info">
                            {stats?.runs.running} {tStatus("running")}
                          </span>
                        </span>
                      ) : null}
                    </span>
                    <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" aria-hidden="true" />
                  </span>
                  <span className="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    {card.getDetails().map((detail) => (
                      <span key={detail.label} className="inline-flex min-w-0 items-center gap-1.5">
                        <span className="font-mono font-medium text-foreground tabular-nums">
                          {detail.value}
                        </span>
                        <span className="truncate">{detail.label}</span>
                      </span>
                    ))}
                  </span>
                </CardContent>
              </Link>
            </CardRoot>
          </div>
        );
      })}
    </div>
  );
}
