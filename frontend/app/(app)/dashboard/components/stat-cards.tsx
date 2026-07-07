"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Play, GitBranch, Container, FolderOpen } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";
import {
  CardRoot,
  CardContent,
} from "@/components/bioinfoflow/card";
import { cn } from "@/lib/utils";
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
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {statCards.map((card, index) => {
        const Icon = card.icon;
        return (
          <motion.div
            key={card.key}
            initial={prefersReducedMotion ? {} : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: index * 0.05, ease: [0.25, 0.1, 0.25, 1.0] }}
            className="h-full"
          >
            <Link href={card.href} className="block h-full">
              <CardRoot
                variant="workbench"
                data-interactive="true"
                className={cn(
                  "group h-full cursor-pointer",
                  card.key === "runs" && "border-foreground/20"
                )}
              >
                <CardContent className="flex h-full flex-col p-4">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <p className="mb-1 text-xs font-medium text-muted-foreground transition-colors group-hover:text-foreground">
                        {tDashboard(card.key)}
                      </p>
                      <p className="font-mono text-3xl font-semibold tracking-tight text-foreground tabular-nums">
                        {card.getValue()}
                      </p>
                      {card.key === "runs" && (stats?.runs.running ?? 0) > 0 && (
                        <div className="flex items-center gap-1.5 mt-1.5">
                          <span className="h-1.5 w-1.5 rounded-full bg-info animate-pulse motion-reduce:animate-none" />
                          <span className="text-xs text-info font-medium">
                            {stats?.runs.running} {tStatus("running")}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="quiet-card-icon-shell size-9 rounded-lg">
                      <Icon className="quiet-card-icon-glyph size-4 transition-colors duration-300" />
                    </div>
                  </div>
                  <div className="mt-auto flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                    {card.getDetails().map((detail, i) => (
                      <span key={i} className="metadata-pill flex items-center gap-1.5 rounded-md border px-2 py-1">
                        <span className="font-mono font-medium text-foreground tabular-nums">
                          {detail.value}
                        </span>
                        <span>{detail.label}</span>
                      </span>
                    ))}
                  </div>
                </CardContent>
              </CardRoot>
            </Link>
          </motion.div>
        );
      })}
    </div>
  );
}
