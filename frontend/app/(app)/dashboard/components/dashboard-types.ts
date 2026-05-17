import type { RunStatus } from "@/lib/types";

export type DashboardStats = {
  runs: {
    total: number;
    running: number;
    completed: number;
    failed: number;
    queued: number;
    pending: number;
    cancelled: number;
  };
  workflows: {
    total: number;
  };
  images: {
    total: number;
    local: number;
    remote: number;
    pulling: number;
  };
  projects: {
    total: number;
  };
  recent_runs: Array<{
    run_id: string;
    workflow_id: string | null;
    status: RunStatus;
    started_at: string | null;
    duration_seconds: number | null;
    current_task: string | null;
  }>;
};

export type SystemHealth = {
  status: string;
  docker: {
    available: boolean;
    nvidia_runtime: boolean;
  };
  gpu: {
    available: boolean;
    parabricks_compatible: boolean;
  };
  parabricks: {
    image_available: boolean;
    image_name: string | null;
  };
};

export type GpuInfo = {
  available: boolean;
  parabricks_compatible: boolean;
  gpus: Array<{
    index: number;
    name: string;
    memory_total_mb: number;
    memory_free_mb: number;
    gpu_type?: string;
  }>;
};

export type ReadinessCheck = {
  id: string;
  label: string;
  status: "pass" | "fail" | "warn" | "skip";
  severity: "blocking" | "optional" | "info";
  detail: string;
  hint?: string | null;
  docs_link?: string | null;
  action_label?: string | null;
  action_href?: string | null;
};

export type ReadinessStatus = {
  severity: "ready" | "blocked";
  next_action: {
    label: string;
    href: string;
  };
  checks: ReadinessCheck[];
  summary?: Record<string, unknown>;
};

export function buildNarrative(
  stats: DashboardStats,
  t: (key: string, values?: Record<string, string | number>) => string,
): string {
  const { runs } = stats;

  if (runs.total === 0) {
    return t("narrativeEmpty");
  }

  const parts: string[] = [];

  if (runs.completed > 0 && runs.completed === runs.total) {
    parts.push(t("narrativeAllComplete", { total: runs.total }));
  } else {
    parts.push(t("narrativeTotal", { total: runs.total }));
    if (runs.completed > 0) {
      parts.push(t("narrativeCompleted", { count: runs.completed }));
    }
    if (runs.running > 0) {
      parts.push(t("narrativeRunning", { count: runs.running }));
    }
    if (runs.failed > 0) {
      parts.push(t("narrativeFailed", { count: runs.failed }));
    }
    if (runs.queued > 0) {
      parts.push(t("narrativeQueued", { count: runs.queued }));
    }
  }

  return t("narrativeJoin", { parts: parts.join(t("narrativeSeparator")) });
}
