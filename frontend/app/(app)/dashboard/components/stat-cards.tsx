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
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
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
              <CardRoot className={cn(
                "group h-full hover:shadow-md transition-all duration-300 cursor-pointer hover:-translate-y-0.5",
                card.key === "runs"
                  ? "border-foreground/20 hover:border-foreground/40"
                  : "hover:border-foreground/30"
              )}>
                <CardContent className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <p className="text-sm text-muted-foreground mb-1 group-hover:text-muted-foreground/80 transition-colors">
                        {tDashboard(card.key)}
                      </p>
                      <p className="text-2xl font-semibold text-foreground tracking-tight">
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
                    <div className="flex items-center justify-center">
                      <Icon className="h-4 w-4 text-muted-foreground/60 group-hover:text-muted-foreground transition-colors duration-300" />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {card.getDetails().map((detail, i) => (
                      <span key={i} className="flex items-center gap-1.5">
                        <span className="font-medium text-foreground">
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
