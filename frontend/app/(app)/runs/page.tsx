"use client"

import { useState } from "react"
import dynamic from "next/dynamic"
import Link from "next/link"
import { AnimatePresence } from "framer-motion"
import { useTranslations } from "next-intl"
import { Search, Filter, Eye, FileText, RotateCcw, XCircle, Trash2, ChevronLeft, ChevronRight, ChevronDown, Play, Layers, Bell } from "lucide-react"
import { authClient } from "@/lib/auth-client"
import {
  canManageDestructiveBusinessActions,
  clientAuthConfig,
  resolveTeamRole,
} from "@/lib/auth-config"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { StatusBadge } from "@/components/ui/status-badge"
import { EmptyState } from "@/components/ui/empty-state"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getCurrentRuntime } from "@/lib/runtime"
import { cn } from "@/lib/utils"
import { runStatusLabel, runStatusVariant } from "@/constants/status-config"
import type { Run, RunStatus } from "@/lib/types"
import { formatDateTime, formatDuration } from "@/lib/format-utils"
import { RunsTableSkeleton } from "./components/runs-table-skeleton"
const RunSubmissionWizard = dynamic(
  () => import("../workflows/components/run-submission-wizard").then((m) => ({ default: m.RunSubmissionWizard })),
  { ssr: false },
)
const NotificationConfigPanel = dynamic(
  () => import("./components/notification-config-panel").then((m) => ({ default: m.NotificationConfigPanel })),
  { ssr: false },
)
const RUNS_TABLE_COLUMN_COUNT = 8
const RunInlineDetail = dynamic(
  () => import("./components/run-inline-detail").then((m) => ({ default: m.RunInlineDetail })),
  {
    ssr: false,
    loading: () => <RunInlineDetailLoadingRow />,
  },
)
import { useRunsPage } from "./use-runs-page"

function RunInlineDetailLoadingRow() {
  const tRuns = useTranslations("runs")

  return (
    <tr data-testid="run-inline-detail-loading">
      <td colSpan={RUNS_TABLE_COLUMN_COUNT} className="p-0">
        <div className="border-l-3 border-primary/30 bg-accent/4 px-6 py-5">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <div className="h-2 w-2 animate-pulse rounded-full bg-primary/55" />
            <span>{tRuns("loadingInlineDetail")}</span>
          </div>
        </div>
      </td>
    </tr>
  )
}

export default function RunsPage() {
  const { data: session } = authClient.useSession()
  const canDeleteWorkspaceRuns = canManageDestructiveBusinessActions(
    clientAuthConfig.mode,
    session?.user ? resolveTeamRole(session.user) : "member",
    clientAuthConfig.authEnabled,
  )
  const {
    tRuns,
    tStatus,
    tCommon,
    isLoading,
    pagination,
    search,
    setSearch,
    statusFilter,
    setStatusFilter,
    expandedRunId,
    expandedRun,
    logs,
    outputs,
    dag,
    batchDialogOpen,
    setBatchDialogOpen,
    notificationPanelOpen,
    setNotificationPanelOpen,
    currentPage,
    highlightRunId,
    effectiveProjectId,
    scope,
    handleScopeChange,
    filteredRuns,
    getPipelineName,
    toggleExpand,
    handleViewLogs,
    handleResume,
    executeCancel,
    handleDelete,
    handleDownloadResults,
    handleRerun,
    handleCleanup,
    handleDownloadFile,
    handlePrevPage,
    handleNextPage,
    handleSubmittedRun,
  } = useRunsPage()

  const [cancelConfirm, setCancelConfirm] = useState<Run | null>(null)
  const confirmCancel = (run: Run) => setCancelConfirm(run)
  const runsColumns: DataTableColumn<Run>[] = [
    {
      key: "chevron",
      header: "",
      width: "w-10",
      align: "center",
      headerClassName: "px-2",
      cellClassName: "px-2",
      cell: (run) => (
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform duration-200 mx-auto",
            expandedRunId === run.run_id && "rotate-180",
          )}
        />
      ),
    },
    {
      key: "runId",
      header: tRuns("runId"),
      cell: (run) => <span className="font-mono text-sm text-foreground">{run.run_id}</span>,
    },
    {
      key: "workflow",
      header: tRuns("workflow"),
      cell: (run) =>
        run.workflow_id ? (
          <Link
            href={`/workflows/${run.workflow_id}`}
            className="text-sm text-muted-foreground transition-colors hover:text-foreground hover:underline underline-offset-4"
            onClick={(event) => event.stopPropagation()}
          >
            {getPipelineName(run)}
          </Link>
        ) : (
          <span className="text-sm text-muted-foreground">{getPipelineName(run)}</span>
        ),
    },
    {
      key: "status",
      header: tRuns("status"),
      cell: (run) => (
        <StatusBadge variant={runStatusVariant[run.status]}>
          {tStatus(runStatusLabel[run.status])}
        </StatusBadge>
      ),
    },
    {
      key: "startTime",
      header: tRuns("startTime"),
      headerClassName: "hidden md:table-cell",
      cellClassName: "hidden md:table-cell text-sm text-muted-foreground",
      cell: (run) => formatDateTime(run.started_at),
    },
    {
      key: "duration",
      header: tRuns("duration"),
      headerClassName: "hidden md:table-cell",
      cellClassName: "hidden md:table-cell text-sm text-muted-foreground font-mono",
      cell: (run) => formatDuration(run.duration_seconds),
    },
    {
      key: "samples",
      header: tRuns("samples"),
      headerClassName: "hidden lg:table-cell",
      cellClassName: "hidden lg:table-cell text-sm text-muted-foreground",
      cell: (run) => run.samples_count,
    },
    {
      key: "actions",
      header: tRuns("actions"),
      align: "right",
      cell: (run) => (
        <RunRowActions
          run={run}
          tRuns={tRuns}
          onToggleExpand={toggleExpand}
          onViewLogs={handleViewLogs}
          onResume={handleResume}
          onCancel={confirmCancel}
          onDelete={handleDelete}
          canDelete={canDeleteWorkspaceRuns}
        />
      ),
    },
  ]

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-5">
          <h1 className="text-xl font-semibold text-foreground">{tRuns("title")}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{tRuns("subtitle")}</p>
        </div>

        {/* Actions Bar */}
        <div className="flex flex-wrap items-center gap-2 sm:gap-4 mb-5">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              id="runs-search"
              placeholder={`${tCommon("search")}...`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
            <Label htmlFor="runs-search" className="sr-only">
              {tCommon("search")} {tRuns("title")}
            </Label>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                <Filter className="h-4 w-4 mr-2" />
                {tCommon("filter")}
                {statusFilter.length > 0 && (
                  <Badge variant="secondary" className="ml-2 h-5 px-1.5">
                    {statusFilter.length}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel>{tCommon("filter")} {tRuns("status")}</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {(Object.keys(runStatusLabel) as RunStatus[]).map((status) => (
                <DropdownMenuCheckboxItem
                  key={status}
                  checked={statusFilter.includes(status)}
                  onCheckedChange={(checked) => {
                    setStatusFilter(checked ? [...statusFilter, status] : statusFilter.filter((s) => s !== status))
                  }}
                >
                  {tStatus(runStatusLabel[status])}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" onClick={() => setBatchDialogOpen(true)}>
            <Layers className="h-4 w-4 mr-2" />
            {tRuns("submitBatch")}
          </Button>
          <Button variant="outline" size="icon" onClick={() => setNotificationPanelOpen(true)} title={tRuns("notifications")}>
            <Bell className="h-4 w-4" />
          </Button>
          <div className="ml-auto">
            <Tabs value={scope} onValueChange={(value) => handleScopeChange(value as "all" | "project")}>
              <TabsList>
                <TabsTrigger value="project" disabled={!effectiveProjectId}>
                  {tRuns("scopes.project")}
                </TabsTrigger>
                <TabsTrigger value="all">
                  {tRuns("scopes.all")}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </div>

        {/* Runs Table */}
        {isLoading ? (
          <RunsTableSkeleton />
        ) : filteredRuns.length === 0 ? (
          <EmptyState
            icon={Play}
            title={tRuns("noRuns")}
            description={tRuns("noRunsDescription")}
          />
        ) : (
          <DataTable<Run>
            columns={runsColumns}
            data={filteredRuns}
            caption={tRuns("tableCaption")}
            rowKey={(run) => run.run_id}
            onRowClick={(run) => toggleExpand(run)}
            rowClassName={(run) => cn(
              expandedRunId === run.run_id && "bg-accent/5",
              highlightRunId === run.run_id && expandedRunId !== run.run_id && "bg-info/10",
            )}
            rowProps={(run) => ({
              tabIndex: 0,
              role: "button" as const,
              "aria-expanded": expandedRunId === run.run_id,
              onKeyDown: (e: React.KeyboardEvent) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  toggleExpand(run)
                }
              },
            })}
            renderAfterRow={(run) => {
              const isExpanded = expandedRunId === run.run_id
              return (
                <AnimatePresence initial={false}>
                  {isExpanded && expandedRun && (
                    <RunInlineDetail
                      key={`${run.run_id}-detail`}
                      run={expandedRun}
                      logs={logs}
                      outputs={outputs}
                      dag={dag}
                      workflowName={getPipelineName(expandedRun)}
                      workflowId={expandedRun.workflow_id}
                      projectId={expandedRun.project_id}
                      onDownloadResults={handleDownloadResults}
                      onRerun={handleRerun}
                      onDelete={handleDelete}
                      onDownloadFile={handleDownloadFile}
                      onCleanup={handleCleanup}
                      colSpan={8}
                    />
                  )}
                </AnimatePresence>
              )
            }}
            className="overflow-x-auto"
          />
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted-foreground">
            {pagination?.total_count
              ? tRuns("pagination.showingOf", { shown: filteredRuns.length, total: pagination.total_count })
              : tRuns("pagination.showing", { shown: filteredRuns.length })}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPage <= 1}
              onClick={handlePrevPage}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-xs text-muted-foreground">{tRuns("pagination.page", { page: currentPage })}</span>
            <Button
              variant="outline"
              size="sm"
              disabled={!pagination?.next_cursor}
              onClick={handleNextPage}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <RunSubmissionWizard
        open={batchDialogOpen}
        onOpenChange={setBatchDialogOpen}
        projectId={effectiveProjectId}
        onSubmitted={handleSubmittedRun}
      />

      <NotificationConfigPanel
        open={notificationPanelOpen}
        onOpenChange={setNotificationPanelOpen}
        projectId={effectiveProjectId}
      />

      {/* Cancel Confirmation Dialog */}
      <Dialog open={!!cancelConfirm} onOpenChange={(open) => !open && setCancelConfirm(null)}>
        <DialogContent showCloseButton={false} data-testid="cancel-confirm-dialog">
          <DialogHeader>
            <DialogTitle>{tRuns("cancelConfirmTitle")}</DialogTitle>
            <DialogDescription>{tRuns("cancelConfirmMessage")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelConfirm(null)}>
              {tCommon("cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (cancelConfirm) {
                  executeCancel(cancelConfirm)
                }
                setCancelConfirm(null)
              }}
            >
              {tCommon("confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function RunRowActions({
  run,
  tRuns,
  onToggleExpand,
  onViewLogs,
  onResume,
  onCancel,
  onDelete,
  canDelete,
}: {
  run: Run
  tRuns: (key: string) => string
  onToggleExpand: (run: Run) => void
  onViewLogs: (run: Run) => void
  onResume: (run: Run) => void
  onCancel: (run: Run) => void
  onDelete: (run: Run) => void
  canDelete: boolean
}) {
  const destructiveActionsEnabled = getCurrentRuntime().capabilities.destructiveActions

  return (
    <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => onToggleExpand(run)}
        title={tRuns("viewDetails")}
        aria-label={tRuns("viewDetails")}
      >
        <Eye className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => onViewLogs(run)}
        title={tRuns("viewLogs")}
        aria-label={tRuns("viewLogs")}
      >
        <FileText className="h-4 w-4" />
      </Button>
      {run.status === "failed" && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => onResume(run)}
          title={tRuns("resumeFromCheckpoint")}
          aria-label={tRuns("resumeFromCheckpoint")}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      )}
      {destructiveActionsEnabled &&
        (run.status === "running" || run.status === "queued" || run.status === "pending") && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-destructive"
          onClick={() => onCancel(run)}
          title={tRuns("cancelRun")}
          aria-label={tRuns("cancelRun")}
        >
          <XCircle className="h-4 w-4" />
        </Button>
      )}
      {destructiveActionsEnabled &&
        canDelete &&
        (run.status === "completed" || run.status === "failed" || run.status === "cancelled") && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-destructive"
          onClick={() => onDelete(run)}
          title={tRuns("deleteRun")}
          aria-label={tRuns("deleteRun")}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      )}
    </div>
  )
}
