"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { ArrowLeft, Activity, Wifi, WifiOff } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { apiRequest, getApiErrorMessage, buildApiUrl } from "@/lib/api";
import { formatDateTime, formatDuration } from "@/lib/format-utils";
import { runStatusLabel, runStatusVariant } from "@/constants/status-config";
import type { DagData, Run, RunLogs, RunOutputs, Workflow } from "@/lib/types";
import { openInNewTab } from "@/lib/window-utils";
import { useProjectContext } from "@/components/bioinfoflow/project-context";
import { useEvents } from "@/hooks/use-events";
import { useSetBreadcrumbDetail } from "@/hooks/use-set-breadcrumb-detail";
import dynamic from "next/dynamic";
import { RunDetailContent } from "../components/run-detail-content";
import { RunStagePanel } from "@/components/bioinfoflow/run-stage-panel";
import { RunErrorCard } from "@/components/bioinfoflow/run-error-card";
import { parseContainerImagePreparationMessage } from "../run-log-toast-utils";

const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);

const DagFullscreenDialog = dynamic(
  () => import("../components/dag-fullscreen-dialog").then((m) => ({ default: m.DagFullscreenDialog })),
  { ssr: false },
);

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const router = useRouter();
  const tRuns = useTranslations("runs");
  const tStatus = useTranslations("status");
  const tCommon = useTranslations("common");
  const { activeProjectId, setActiveProjectId } = useProjectContext();

  const runId = params.runId;
  const [run, setRun] = useState<Run | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [logs, setLogs] = useState<RunLogs | null>(null);
  const [outputs, setOutputs] = useState<RunOutputs | null>(null);
  const [dag, setDag] = useState<DagData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [dagFullscreen, setDagFullscreen] = useState(false);
  const imagePreparationToastKeysRef = useRef(new Set<string>());

  useSetBreadcrumbDetail(runId);

  const workflowName = (() => {
    if (!workflow) return run?.workflow_id ?? "";
    return workflow.source === "nf-core" &&
      !workflow.name.startsWith("nf-core/")
      ? `nf-core/${workflow.name}`
      : workflow.name;
  })();

  const refreshArtifacts = useCallback(async () => {
    try {
      const outputsRes = await apiRequest<RunOutputs>(`/runs/${runId}/outputs`);
      setOutputs(outputsRes.data);
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.loadRunDetailsFailed"));
      toast.error(message);
    }
  }, [runId, tRuns]);

  const maybeToastImagePreparation = useCallback((message: string) => {
    const images = parseContainerImagePreparationMessage(message);
    if (!images) return;
    const key = `${runId}:${message}`;
    if (imagePreparationToastKeysRef.current.has(key)) return;
    imagePreparationToastKeysRef.current.add(key);
    toast.info(tRuns("toasts.preparingImagesTitle"), {
      description: images,
    });
  }, [runId, tRuns]);

  const fetchRun = useCallback(async () => {
    setIsLoading(true);
    try {
      const { data } = await apiRequest<Run>(`/runs/${runId}`);
      setRun(data);

      // Fetch workflow name
      if (data.workflow_id) {
        try {
          const { data: wf } = await apiRequest<Workflow>(
            `/workflows/${data.workflow_id}`,
          );
          setWorkflow(wf);
        } catch {
          // Workflow may have been deleted
        }
      }

      // Fetch details in parallel
      const [logsRes, outputsRes, dagRes] = await Promise.all([
        apiRequest<RunLogs>(`/runs/${runId}/logs`, { params: { tail: 200 } }),
        apiRequest<RunOutputs>(`/runs/${runId}/outputs`),
        apiRequest<DagData>(`/runs/${runId}/dag`),
      ]);
      setLogs(logsRes.data);
      setOutputs(outputsRes.data);
      setDag(dagRes.data);
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.loadRunDetailsFailed"));
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [runId, tRuns]);

  useEffect(() => {
    fetchRun();
  }, [fetchRun]);

  useEffect(() => {
    if (!run?.project_id || run.project_id === activeProjectId) {
      return;
    }
    setActiveProjectId(run.project_id);
  }, [activeProjectId, run?.project_id, setActiveProjectId]);

  // SSE for real-time updates
  const { connectionState } = useEvents({
    projectId: run?.project_id,
    runId,
    onRunStatus: (envelope) => {
      if (envelope.data.run_id !== runId) return;
      const { status, current_task, tasks_completed, tasks_total } =
        envelope.data;
      setRun((prev) => {
        if (!prev) return prev;
        const updates: Partial<Run> = {
          status,
          current_task: current_task ?? null,
        };
        if (typeof tasks_completed === "number")
          updates.tasks_completed = tasks_completed;
        if (typeof tasks_total === "number") updates.tasks_total = tasks_total;
        return { ...prev, ...updates };
      });
      if (TERMINAL_RUN_STATUSES.has(status)) {
        void refreshArtifacts();
      }
    },
    onRunLog: (envelope) => {
      if (envelope.data.run_id !== runId) return;
      const { message, level, task, timestamp } = envelope.data;
      maybeToastImagePreparation(message);
      setLogs((prev) => {
        const existing = prev?.logs ?? [];
        const next = [
          ...existing,
          {
            message,
            level: level ?? null,
            task: task ?? null,
            timestamp: timestamp ?? null,
          },
        ].slice(-500);
        return { logs: next };
      });
    },
    onRunDag: (envelope) => {
      if (envelope.data.run_id !== runId) return;
      setDag(envelope.data.dag);
    },
  });

  const handleDelete = (targetRun: Run) => {
    toast.warning(
      tRuns("toasts.deleteConfirmTitle", { runId: targetRun.run_id }),
      {
        description: tRuns("toasts.deleteConfirmDescription"),
        action: {
          label: tCommon("confirm"),
          onClick: async () => {
            try {
              await apiRequest(`/runs/${targetRun.run_id}`, {
                method: "DELETE",
              });
              toast.success(
                tRuns("toasts.deletedTitle", { runId: targetRun.run_id }),
              );
              router.push("/runs");
            } catch (error) {
              const message = getApiErrorMessage(error, tRuns("errors.deleteFailed"));
              toast.error(message);
            }
          },
        },
      },
    );
  };

  const handleRerun = async (targetRun: Run) => {
    try {
      await apiRequest(`/runs/${targetRun.run_id}/retry`, { method: "POST" });
      toast.success(
        tRuns("toasts.resubmittedTitle", { runId: targetRun.run_id }),
        {
          description: tRuns("toasts.checkRunsPage"),
        },
      );
      router.push("/runs");
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.retryFailed"));
      toast.error(message);
    }
  };

  const handleDownloadResults = (targetRun: Run) => {
    const url = buildApiUrl(`/runs/${targetRun.run_id}/outputs/download`, {
      format: "tar.gz",
    });
    openInNewTab(url);
  };

  const handleDownloadFile = (path: string) => {
    const url = buildApiUrl(`/runs/${runId}/outputs/download`, {
      file: path,
      format: "tar.gz",
    });
    openInNewTab(url);
  };

  const progressPercent = run?.tasks_total
    ? Math.round(((run.tasks_completed ?? 0) / run.tasks_total) * 100)
    : null;

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="p-4 sm:p-6 max-w-6xl mx-auto">
          <Skeleton className="h-8 w-32 mb-6" />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-5">
            <div className="space-y-3">
              <Skeleton className="h-6 w-40" />
              <Skeleton className="h-24 w-full rounded-2xl" />
              <Skeleton className="h-24 w-full rounded-2xl" />
            </div>
            <div>
              <Skeleton className="h-[420px] lg:h-[500px] w-full" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="h-full overflow-y-auto">
        <div className="p-4 sm:p-6 max-w-6xl mx-auto">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/runs")}
            className="mb-4"
          >
            <ArrowLeft className="h-4 w-4 mr-1.5" />
            {tRuns("backToRuns")}
          </Button>
          <p className="text-muted-foreground">
            {tRuns("errors.loadRunDetailsFailed")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        {/* Breadcrumb / Back */}
        <div className="flex flex-wrap items-center gap-2 mb-5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/runs")}
          >
            <ArrowLeft className="h-4 w-4 mr-1.5" />
            {tRuns("backToRuns")}
          </Button>
          <span className="text-muted-foreground text-sm">/</span>
          <span className="text-sm font-mono text-foreground truncate">
            {run.run_id}
          </span>
          {connectionState === "reconnecting" && (
            <Badge variant="outline" className="ml-auto text-amber-600 border-amber-300 bg-amber-50 dark:text-amber-400 dark:border-amber-700 dark:bg-amber-950">
              <Wifi className="h-3 w-3" />
              <span className="hidden sm:inline">{tRuns("detail.connectionReconnecting")}</span>
            </Badge>
          )}
          {connectionState === "disconnected" && (
            <Badge variant="outline" className="ml-auto text-destructive border-destructive/30 bg-destructive/5">
              <WifiOff className="h-3 w-3" />
              <span className="hidden sm:inline">{tRuns("detail.connectionDisconnected")}</span>
            </Badge>
          )}
        </div>

        {/* Two-column layout (stacks on mobile/tablet) */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-5">
          {/* Left panel — Run info */}
          <div className="space-y-3 min-w-0">
            {/* Run ID + Status */}
            <div className="rounded-2xl border border-border/60 bg-card p-4 space-y-2.5">
              <div className="min-w-0">
                <h2 className="font-mono text-[15px] font-semibold tracking-tight truncate">
                  {run.run_id}
                </h2>
                <div className="flex items-center gap-2 mt-1.5">
                  <StatusBadge variant={runStatusVariant[run.status]}>
                    {tStatus(runStatusLabel[run.status] ?? run.status)}
                  </StatusBadge>
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-[13px] text-muted-foreground min-w-0">
                <Activity className="w-3.5 h-3.5 shrink-0" />
                {run.workflow_id ? (
                  <Link
                    href={`/workflows/${run.workflow_id}`}
                    className="truncate transition-colors hover:text-foreground hover:underline underline-offset-4"
                  >
                    {workflowName}
                  </Link>
                ) : (
                  <span className="truncate">{workflowName}</span>
                )}
              </div>
            </div>

            {/* Metadata */}
            <div className="rounded-2xl border border-border/60 bg-card p-4 space-y-0">
              <MetaField
                label={tRuns("detail.started")}
                value={formatDateTime(run.started_at)}
              />
              <MetaField
                label={tRuns("detail.duration")}
                value={formatDuration(run.duration_seconds)}
                mono
              />
              <MetaField
                label={tRuns("detail.workspace")}
                value={`runs/${run.run_id}`}
                mono
              />
              <MetaField
                label={tRuns("samples")}
                value={String(run.samples_count ?? "-")}
              />
              {run.current_task && (
                <MetaField
                  label={tRuns("currentTask")}
                  value={run.current_task}
                />
              )}
            </div>

            {/* Progress */}
            {progressPercent !== null && (
              <div className="rounded-2xl border border-border/60 bg-card p-4 space-y-2">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-medium">
                    {tRuns("progress")}
                  </span>
                  <span>
                    {run.tasks_completed ?? 0} / {run.tasks_total}
                  </span>
                </div>
                <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all duration-500",
                      run.status === "failed" ? "bg-destructive" : "bg-primary",
                    )}
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Right panel — Content */}
          <div className="min-w-0 space-y-3">
            <RunStagePanel status={run.status} currentTask={run.current_task} />
            <RunErrorCard error={run.error} />
            <div className="rounded-2xl border border-border/60 bg-card overflow-hidden flex flex-col min-h-[560px] lg:min-h-[640px]">
              <RunDetailContent
                run={run}
                logs={logs}
                outputs={outputs}
                dag={dag}
                workflowName={workflowName}
                projectId={run.project_id}
                variant="fullpage"
              onDownloadResults={handleDownloadResults}
              onRerun={handleRerun}
              onDelete={handleDelete}
              onDownloadFile={handleDownloadFile}
              onOpenDagFullscreen={() => setDagFullscreen(true)}
            />
            </div>
          </div>
        </div>
      </div>

      <DagFullscreenDialog
        open={dagFullscreen}
        onOpenChange={setDagFullscreen}
        runId={runId}
        dag={dag}
        workflowName={workflowName}
      />
    </div>
  );
}

function MetaField({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/40 px-0 py-2.5 last:border-b-0">
      <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground shrink-0">
        {label}
      </p>
      <p
        className={cn("text-[13px] text-foreground truncate text-right", mono && "font-mono")}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
