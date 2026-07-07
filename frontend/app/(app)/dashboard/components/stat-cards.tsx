"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Play, GitBranch, Container, FolderOpen } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import { CardRoot } from "@/components/bioinfoflow/card";
import type { DashboardStats } from "./dashboard-types";

type StatCardsProps = {
  stats: DashboardStats | null;
};

export function StatCards({ stats }: StatCardsProps) {
  const tDashboard = useTranslations("dashboard");
  const tStatus = useTranslations("status");
  const prefersReducedMotion = useReducedMotion();

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
    <CardRoot
      variant="workbench"
      className="overflow-hidden"
      data-testid="dashboard-metric-strip"
    >
      <div className="bif-dashboard-metric-grid">
        {statCards.map((card, index) => {
          const Icon = card.icon;
          return (
            <motion.div
              key={card.key}
              initial={prefersReducedMotion ? {} : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.05, ease: [0.25, 0.1, 0.25, 1.0] }}
            >
              <Link
                href={card.href}
                className="group flex min-h-[5.875rem] min-w-0 flex-col justify-between gap-2.5 px-4 py-3 transition-colors hover:bg-muted/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-inset min-[360px]:min-h-[4.875rem] min-[360px]:px-3.5 min-[360px]:py-2.5 lg:min-h-[5.875rem] lg:px-4 lg:py-3"
              >
                <span className="flex min-w-0 items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="inline-flex max-w-full items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors group-hover:text-foreground">
                      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
                      <span className="truncate">{tDashboard(card.key)}</span>
                    </span>
                    <span className="mt-1 block font-mono text-2xl font-semibold tracking-tight text-foreground tabular-nums">
                      {card.getValue()}
                    </span>
                    {card.key === "runs" && (stats?.runs.running ?? 0) > 0 ? (
                      <span className="mt-1.5 flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-info animate-pulse motion-reduce:animate-none" />
                        <span className="text-xs font-medium text-info">
                          {stats?.runs.running} {tStatus("running")}
                        </span>
                      </span>
                    ) : null}
                  </span>
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
              </Link>
            </motion.div>
          );
        })}
      </div>
    </CardRoot>
  );
}
