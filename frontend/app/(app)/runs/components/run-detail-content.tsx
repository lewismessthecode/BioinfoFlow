"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  Play,
  Trash2,
  Terminal,
  FileJson,
  Maximize2,
  Eraser,
  MoreHorizontal,
  FolderOpen,
} from "@/lib/icons";
import { useTranslations } from "next-intl";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/ui/empty-state";
import { authClient } from "@/lib/auth-client";
import {
  canManageDestructiveBusinessActions,
  clientAuthConfig,
  resolveTeamRole,
} from "@/lib/auth-config";
import { getCurrentRuntime } from "@/lib/runtime";
import { cn } from "@/lib/utils";
import { formatSize } from "@/lib/format-utils";
import { DagPanel } from "@/components/bioinfoflow/dag";
import { useTerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock-context";
import { apiRequest, ApiError, buildApiUrl } from "@/lib/api";
import { toast } from "sonner";
import type { DagData, Run, RunLogs, RunOutputs } from "@/lib/types";
import {
  type OutputTreeNode,
  type PreviewState,
  MAX_PREVIEW_LINES,
  MAX_TABLE_ROWS,
  buildOutputTree,
  parseDelimitedTable,
  isBinaryPath,
  isImagePath,
  isJsonPath,
  isTablePath,
} from "./run-detail-utils";
import { RunAuditTab } from "./run-audit-tab";

export interface RunDetailContentProps {
  run: Run;
  logs: RunLogs | null;
  outputs: RunOutputs | null;
  dag: DagData | null;
  workflowName: string;
  projectId: string;
  variant: "inline" | "fullpage";
  onDownloadResults: (run: Run) => void;
  onRerun: (run: Run) => void;
  onDelete: (run: Run) => void;
  onDownloadFile: (path: string) => void;
  onOpenDagFullscreen?: () => void;
  onCleanup?: (run: Run) => void;
}

export function RunDetailContent({
  run,
  logs,
  outputs,
  dag,
  workflowName,
  projectId,
  variant,
  onDownloadResults,
  onRerun,
  onDelete,
  onDownloadFile,
  onOpenDagFullscreen,
  onCleanup,
}: RunDetailContentProps) {
  const tRuns = useTranslations("runs");
  const tCommon = useTranslations("common");
  const { data: session } = authClient.useSession();
  const { chdir, isOpen: isTerminalOpen } = useTerminalDock();
  const runtime = getCurrentRuntime();
  const destructiveActionsEnabled =
    runtime.capabilities.destructiveActions &&
    canManageDestructiveBusinessActions(
      clientAuthConfig.mode,
      session?.user ? resolveTeamRole(session.user) : "member",
      clientAuthConfig.authEnabled,
    );

  const outputTree = useMemo(
    () => buildOutputTree(outputs?.files ?? []),
    [outputs?.files],
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState>({ kind: "none" });

  useEffect(() => {
    setExpanded(new Set());
    setSelectedPath(null);
    setPreview({ kind: "none" });
  }, [run.run_id]);

  useEffect(() => {
    const controller = new AbortController();

    const load = async () => {
      if (!selectedPath || !projectId) return;
      const path = selectedPath;

      if (isImagePath(path)) {
        const src = buildApiUrl("/files/download", {
          project_id: projectId,
          path,
        });
        setPreview({ kind: "image", path, src });
        return;
      }
      if (isBinaryPath(path)) {
        setPreview({ kind: "binary", path });
        return;
      }

      setPreview({ kind: "loading", path });
      try {
        const { data } = await apiRequest<{ content: string }>("/files/read", {
          params: {
            project_id: projectId,
            path,
            lines: MAX_PREVIEW_LINES,
            offset: 0,
          },
          signal: controller.signal,
        });
        const raw = data.content ?? "";

        if (isTablePath(path)) {
          const delimiter = path.toLowerCase().endsWith(".tsv") ? "\t" : ",";
          const table = parseDelimitedTable(raw, delimiter);
          setPreview({ kind: "table", path, ...table });
          return;
        }

        if (isJsonPath(path)) {
          try {
            const parsed = JSON.parse(raw);
            setPreview({
              kind: "json",
              path,
              content: JSON.stringify(parsed, null, 2),
            });
            return;
          } catch {
            // Fall back to text if the file is not valid JSON.
          }
        }

        setPreview({ kind: "text", path, content: raw });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        const message =
          error instanceof ApiError
            ? error.message
            : tRuns("errors.previewFailed");
        setPreview({ kind: "error", path, message });
        toast.error(message);
      }
    };

    load();
    return () => controller.abort();
  }, [projectId, selectedPath, tRuns]);

  const toggleExpanded = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const OutputTreeItem = ({
    node,
    depth,
  }: {
    node: OutputTreeNode;
    depth: number;
  }) => {
    const isDir = node.type === "directory";
    const isOpen = expanded.has(node.path);
    const isSelected = selectedPath === node.path;
    return (
      <div>
        <button
          className={cn(
            "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-secondary transition-colors",
            isSelected && "bg-secondary",
          )}
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
          onClick={() => {
            if (isDir) toggleExpanded(node.path);
            else setSelectedPath(node.path);
          }}
        >
          <span className="text-muted-foreground shrink-0 w-4 text-center">
            {isDir ? (isOpen ? "▾" : "▸") : ""}
          </span>
          <span className="min-w-0 flex-1 truncate text-left">{node.name}</span>
          {node.type === "file" ? (
            <span className="text-xs text-muted-foreground shrink-0">
              {formatSize(node.size_bytes ?? null)}
            </span>
          ) : null}
        </button>
        {isDir && isOpen && node.children?.length ? (
          <div>
            {node.children.map((child) => (
              <OutputTreeItem key={child.path} node={child} depth={depth + 1} />
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const isInline = variant === "inline";
  const dagHeight = isInline ? "h-[420px]" : "h-full";

  const tabTriggerClass =
    "rounded-lg px-3 py-1 text-[12px] font-medium data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:ring-1 data-[state=active]:ring-border/10 transition-all hover:text-foreground/80";

  return (
    <div
      className={cn("flex flex-col min-h-0", isInline ? "" : "flex-1 h-full")}
    >
      {run.status === "failed" && run.error_message && (
        <CollapsibleErrorAlert message={run.error_message} className="mx-4 mt-3" />
      )}
      <Tabs
        defaultValue="dag"
        className="flex-1 h-full min-h-0 flex flex-col gap-0"
      >
        <div className="px-3 py-2 border-b border-border/60 bg-background/50 backdrop-blur-sm flex flex-wrap items-center justify-between gap-2 sm:px-4">
          <TabsList className="h-9 w-auto inline-flex items-center justify-start rounded-lg bg-muted/50 p-1 border border-border/40 max-w-full overflow-x-auto">
            <TabsTrigger value="dag" className={tabTriggerClass}>
              {tRuns("detail.tabs.dag")}
            </TabsTrigger>
            <TabsTrigger value="logs" className={tabTriggerClass}>
              {tRuns("detail.tabs.logs")}
            </TabsTrigger>
            <TabsTrigger value="files" className={tabTriggerClass}>
              {tRuns("detail.tabs.files")}
            </TabsTrigger>
            <TabsTrigger value="audit" className={tabTriggerClass}>
              {tRuns("detail.tabs.audit")}
            </TabsTrigger>
          </TabsList>

          {/* Actions: primary + overflow menu */}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => onRerun(run)}
            >
              <Play className="w-3.5 h-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">{tRuns("rerunPipeline")}</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDownloadResults(run)}
              disabled={run.status !== "completed" && run.status !== "failed"}
            >
              <Download className="w-3.5 h-3.5 sm:mr-1.5" />
              <span className="hidden sm:inline">{tRuns("downloadResults")}</span>
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {isTerminalOpen ? (
                  <DropdownMenuItem onClick={() => chdir(`runs/${run.run_id}`)}>
                    <FolderOpen className="w-3.5 h-3.5 mr-2" />
                    {tRuns("goToRunDir")}
                  </DropdownMenuItem>
                ) : null}
                {destructiveActionsEnabled &&
                  onCleanup &&
                  (run.status === "completed" || run.status === "failed" || run.status === "cancelled") && (
                  <DropdownMenuItem onClick={() => onCleanup(run)}>
                    <Eraser className="w-3.5 h-3.5 mr-2" />
                    {tRuns("cleanupRun")}
                  </DropdownMenuItem>
                )}
                {destructiveActionsEnabled ? <DropdownMenuSeparator /> : null}
                {destructiveActionsEnabled ? (
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={() => onDelete(run)}
                  >
                    <Trash2 className="w-3.5 h-3.5 mr-2" />
                    {tRuns("deleteRun")}
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <div
          className={cn(
            "flex flex-1 min-h-0 bg-secondary/5 overflow-hidden",
            isInline && "max-h-[460px]",
          )}
        >
          <TabsContent value="dag" className="m-0 flex-1 min-h-0 p-0">
            <div
              className={cn(
                "relative",
                isInline ? dagHeight : "h-full min-h-[420px]",
              )}
            >
              <DagPanel
                variant="embedded"
                runId={run.run_id}
                dag={dag}
                theme="classic"
                workflowName={workflowName}
                showHeader={false}
              />
              {onOpenDagFullscreen && (
                <Button
                  variant="outline"
                  size="sm"
                  className="absolute top-3 right-3 z-10 bg-background/80 backdrop-blur-sm"
                  onClick={onOpenDagFullscreen}
                >
                  <Maximize2 className="w-3.5 h-3.5 mr-1.5" />
                  {tRuns("fullscreen")}
                </Button>
              )}
            </div>
          </TabsContent>

          <TabsContent
            value="logs"
            className="m-0 flex-1 min-h-0 overflow-auto p-4"
          >
            <div className="rounded-lg border border-border bg-card shadow-sm p-4 font-mono text-xs leading-relaxed overflow-x-auto">
              {logs?.logs?.length ? (
                <div className="flex flex-col gap-0.5">
                  {logs.logs.length >= 500 && (
                    <p className="text-xs text-muted-foreground px-3 py-1.5 border-b">
                      {tRuns("detail.logsTruncated", { count: 500 })}
                    </p>
                  )}
                  {logs.logs.map((entry, index) => (
                    <div
                      key={`${entry.message}-${index}`}
                      className="flex gap-3 hover:bg-muted/30 px-1 -mx-1 rounded"
                    >
                      <span className="text-muted-foreground/50 select-none shrink-0 w-8 text-right">
                        {index + 1}
                      </span>
                      <span className="text-foreground/90 whitespace-pre-wrap break-all">
                        {entry.message}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Terminal}
                  title={tRuns("detail.logs.empty")}
                  description={tRuns("detail.logs.emptyDescription")}
                  className="py-12"
                />
              )}
            </div>
          </TabsContent>

          <TabsContent
            value="files"
            className="m-0 flex-1 min-h-0 overflow-auto p-4"
          >
            {!outputs?.files?.length ? (
              <EmptyState
                icon={FileJson}
                title={tRuns("detail.outputs.empty")}
                description={
                  run.status === "running" || run.status === "pending" || run.status === "queued"
                    ? tRuns("detail.outputsEmptyRunning")
                    : run.status === "failed"
                      ? tRuns("detail.outputsEmptyFailed")
                      : tRuns("detail.outputsEmptyCompleted")
                }
                className="py-12"
              />
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4 h-full">
                <div className="rounded-lg border border-border bg-card shadow-sm p-3 overflow-auto">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {tRuns("detail.outputs.title")}
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setExpanded(
                          new Set(
                            outputTree
                              .filter((n) => n.type === "directory")
                              .map((n) => n.path),
                          ),
                        );
                      }}
                    >
                      {tRuns("detail.outputs.expandAll")}
                    </Button>
                  </div>
                  <div className="space-y-0.5">
                    {outputTree.map((node) => (
                      <OutputTreeItem key={node.path} node={node} depth={0} />
                    ))}
                  </div>
                </div>

                <div className="rounded-lg border border-border bg-card shadow-sm overflow-hidden flex flex-col min-h-[320px]">
                  <div className="border-b border-border/60 px-4 py-3 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">
                        {selectedPath
                          ? selectedPath.split("/").pop()
                          : tRuns("detail.outputs.selectFile")}
                      </p>
                      <p className="text-xs text-muted-foreground font-mono truncate">
                        {selectedPath || "—"}
                      </p>
                    </div>
                    {selectedPath ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onDownloadFile(selectedPath)}
                      >
                        <Download className="h-4 w-4 mr-2" />
                        {tCommon("download")}
                      </Button>
                    ) : null}
                  </div>

                  <div className="flex-1 overflow-auto p-4">
                    {preview.kind === "none" ? (
                      <div className="text-sm text-muted-foreground">
                        {tRuns("detail.outputs.chooseFileToPreview")}
                      </div>
                    ) : preview.kind === "loading" ? (
                      <div className="text-sm text-muted-foreground">
                        {tRuns("detail.outputs.loadingPreview")}
                      </div>
                    ) : preview.kind === "error" ? (
                      <div className="text-sm text-destructive">
                        {preview.message}
                      </div>
                    ) : preview.kind === "binary" ? (
                      <div className="space-y-2">
                        <p className="text-sm text-muted-foreground">
                          {tRuns("detail.outputs.binaryNotPreviewed")}
                        </p>
                      </div>
                    ) : preview.kind === "image" ? (
                      <div className="flex items-center justify-center">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={preview.src}
                          alt={preview.path}
                          className="max-h-[60vh] md:max-h-[520px] w-auto rounded-md border border-border"
                        />
                      </div>
                    ) : preview.kind === "table" ? (
                      <div className="space-y-3">
                        <div className="overflow-auto rounded-md border border-border">
                          <table className="w-full text-xs">
                            <thead className="bg-secondary/40">
                              <tr>
                                {preview.header.map((h, i) => (
                                  <th
                                    key={`${h}-${i}`}
                                    className="text-left font-medium text-muted-foreground px-3 py-2 whitespace-nowrap"
                                  >
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {preview.rows.map((row, rIdx) => (
                                <tr
                                  key={rIdx}
                                  className="border-t border-border/60"
                                >
                                  {row.map((cell, cIdx) => (
                                    <td
                                      key={cIdx}
                                      className="px-3 py-2 font-mono text-foreground/90 whitespace-nowrap"
                                    >
                                      {cell}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {preview.truncated ? (
                          <p className="text-xs text-muted-foreground">
                            {tRuns("detail.outputs.showingFirstRows", {
                              count: MAX_TABLE_ROWS,
                            })}
                          </p>
                        ) : null}
                      </div>
                    ) : (
                      <pre className="text-xs leading-relaxed font-mono whitespace-pre-wrap break-words">
                        {preview.content}
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            )}
          </TabsContent>

          <TabsContent
            value="audit"
            className="m-0 flex-1 min-h-0 overflow-auto"
          >
            <RunAuditTab runId={run.run_id} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

const ERROR_PREVIEW_LINES = 2;

function CollapsibleErrorAlert({
  message,
  className,
}: {
  message: string;
  className?: string;
}) {
  const tRuns = useTranslations("runs");
  const [expanded, setExpanded] = useState(false);

  const lines = useMemo(() => message.split(/\r?\n/), [message]);
  const isLong =
    lines.length > ERROR_PREVIEW_LINES || message.length > 240;
  const previewLines = lines.slice(0, ERROR_PREVIEW_LINES);
  const previewText =
    previewLines.join("\n") + (lines.length > ERROR_PREVIEW_LINES ? "…" : "");

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message);
      toast.success(tRuns("detail.error.copied"));
    } catch {
      toast.error(tRuns("detail.error.copyFailed"));
    }
  };

  return (
    <Alert variant="destructive" className={cn("relative", className)}>
      <AlertCircle className="h-4 w-4" />
      <AlertTitle className="flex items-center justify-between gap-2 pr-2">
        <span>{tRuns("detail.errorTitle")}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs gap-1 -my-1"
          onClick={handleCopy}
        >
          <Copy className="h-3 w-3" />
          {tRuns("detail.error.copy")}
        </Button>
      </AlertTitle>
      <AlertDescription>
        {!expanded ? (
          <pre className="font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words text-foreground/80 max-w-full">
            {previewText}
          </pre>
        ) : (
          <div className="rounded-md border border-destructive/20 bg-background/40 max-h-96 overflow-auto">
            <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-words p-3 text-foreground/90">
              {message}
            </pre>
          </div>
        )}
        {isLong && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-foreground/80 hover:text-foreground transition-colors"
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            {expanded
              ? tRuns("detail.error.collapse")
              : tRuns("detail.error.expand")}
          </button>
        )}
      </AlertDescription>
    </Alert>
  );
}
