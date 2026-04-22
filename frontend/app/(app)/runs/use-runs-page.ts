"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage, buildApiUrl } from "@/lib/api"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useEvents } from "@/hooks/use-events"
import type { DagData, Pagination, Run, RunLogs, RunOutputs, RunStatus, Workflow } from "@/lib/types"
import { openInNewTab } from "@/lib/window-utils"

type RunsScope = "all" | "project"
const TERMINAL_RUN_STATUSES = new Set<RunStatus>(["completed", "failed", "cancelled"])

function resolveRunsScope(scopeParam: string | null, projectId: string | null): RunsScope {
  if (scopeParam === "all") return "all"
  if (scopeParam === "project") return projectId ? "project" : "all"
  return projectId ? "project" : "all"
}

export function useRunsPage() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const searchParamsString = searchParams.toString()
  const tRuns = useTranslations("runs")
  const tStatus = useTranslations("status")
  const tCommon = useTranslations("common")
  const { activeProjectId, setActiveProjectId } = useProjectContext()
  const [runs, setRuns] = useState<Run[]>([])
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [pagination, setPagination] = useState<Pagination | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([])
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState<RunStatus[]>([])
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null)
  const [logs, setLogs] = useState<RunLogs | null>(null)
  const [outputs, setOutputs] = useState<RunOutputs | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)
  const [batchDialogOpen, setBatchDialogOpen] = useState(false)
  const [notificationPanelOpen, setNotificationPanelOpen] = useState(false)
  const itemsPerPage = 20
  const currentPage = cursorHistory.length + 1
  const highlightRunId = searchParams.get("highlight")
  const urlProjectId = searchParams.get("project_id")
  const urlScope = searchParams.get("scope")
  const expandedRunIdRef = useRef(expandedRunId)
  const consumedHighlightRef = useRef<string | null>(null)
  expandedRunIdRef.current = expandedRunId

  const effectiveProjectId = urlProjectId || activeProjectId || null
  const [scope, setScope] = useState<RunsScope>(() => resolveRunsScope(urlScope, effectiveProjectId))

  useEffect(() => {
    if (urlProjectId && urlProjectId !== activeProjectId) {
      setActiveProjectId(urlProjectId)
    }
  }, [urlProjectId, activeProjectId, setActiveProjectId])

  useEffect(() => {
    setScope(resolveRunsScope(urlScope, effectiveProjectId))
  }, [urlScope, effectiveProjectId])

  const updateScopeUrl = useCallback((nextScope: RunsScope) => {
    const params = new URLSearchParams(searchParamsString)
    params.set("scope", nextScope)
    if (nextScope === "all") {
      params.delete("project_id")
    }
    const query = params.toString()
    router.replace(query ? `${pathname}?${query}` : pathname)
  }, [pathname, router, searchParamsString])

  const handleScopeChange = useCallback((nextScope: RunsScope) => {
    const resolvedScope = nextScope === "project" && effectiveProjectId ? "project" : "all"
    setScope(resolvedScope)
    updateScopeUrl(resolvedScope)
  }, [effectiveProjectId, updateScopeUrl])

  const workflowNameMap = useMemo(() => {
    const map = new Map<string, string>()
    workflows.forEach((workflow) => {
      map.set(workflow.id, workflow.source === "nf-core" && !workflow.name.startsWith("nf-core/")
        ? `nf-core/${workflow.name}`
        : workflow.name)
    })
    return map
  }, [workflows])

  const fetchWorkflows = useCallback(async () => {
    try {
      const { data } = await apiRequest<Workflow[]>("/workflows", {
        params: { limit: 200 },
      })
      setWorkflows(data)
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.loadWorkflowsFailed"))
      toast.error(message)
    }
  }, [tRuns])

  const fetchRuns = useCallback(async (cursorOverride?: string | null) => {
    setIsLoading(true)
    try {
      const minLoadTime = new Promise((resolve) => setTimeout(resolve, 500))
      const effectiveCursor = cursorOverride === undefined ? cursor : cursorOverride

      const [{ data, meta }] = await Promise.all([
        apiRequest<Run[]>("/runs", {
          params: {
            limit: itemsPerPage,
            cursor: effectiveCursor || undefined,
            project_id: scope === "project" ? effectiveProjectId || undefined : undefined,
            status: statusFilter.length ? statusFilter.join(",") : undefined,
          },
        }),
        minLoadTime
      ])

      setRuns(data)
      setPagination(meta?.pagination ?? null)
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.loadRunsFailed"))
      toast.error(message)
    } finally {
      setIsLoading(false)
    }
  }, [cursor, effectiveProjectId, itemsPerPage, scope, statusFilter, tRuns])

  const reloadExpandedArtifacts = useCallback(async (runId: string) => {
    try {
      const outputsResponse = await apiRequest<RunOutputs>(`/runs/${runId}/outputs`)
      if (expandedRunIdRef.current !== runId) return
      setOutputs(outputsResponse.data)
    } catch (error) {
      if (expandedRunIdRef.current !== runId) return
      const message = getApiErrorMessage(error, tRuns("errors.loadRunDetailsFailed"))
      toast.error(message)
    }
  }, [tRuns])

  const handleRunStatus = useCallback((runId: string, updates: Partial<Run>) => {
    setRuns((prev) =>
      prev.map((run) => (run.run_id === runId ? { ...run, ...updates } : run))
    )
  }, [])

  const handleRunLogEvent = useCallback(
    (runId: string, entry: RunLogs["logs"][number]) => {
      setLogs((prev) => {
        if (expandedRunIdRef.current !== runId) return prev
        const existing = prev?.logs ?? []
        const next = [...existing, entry].slice(-500)
        return { logs: next }
      })
    },
    []
  )

  useEvents({
    projectId: scope === "project" ? effectiveProjectId || undefined : undefined,
    onRunStatus: (envelope) => {
      const { run_id, status, current_task, tasks_completed, tasks_total } = envelope.data
      const updates: Partial<Run> = {
        status,
        current_task: current_task ?? null,
      }
      if (typeof tasks_completed === "number") {
        updates.tasks_completed = tasks_completed
      }
      if (typeof tasks_total === "number") {
        updates.tasks_total = tasks_total
      }
      handleRunStatus(run_id, updates)
      if (
        expandedRunIdRef.current === run_id &&
        TERMINAL_RUN_STATUSES.has(status)
      ) {
        void reloadExpandedArtifacts(run_id)
      }
    },
    onRunLog: (envelope) => {
      const { run_id, message, level, task, timestamp } = envelope.data
      handleRunLogEvent(run_id, { message, level: level ?? null, task: task ?? null, timestamp: timestamp ?? null })
    },
    onRunDag: (envelope) => {
      if (expandedRunIdRef.current !== envelope.data.run_id) return
      setDag(envelope.data.dag)
    },
  })

  useEffect(() => {
    fetchWorkflows()
  }, [fetchWorkflows])

  useEffect(() => {
    fetchRuns()
  }, [fetchRuns])

  // Auto-expand highlighted run from URL params
  useEffect(() => {
    if (!highlightRunId) return
    if (consumedHighlightRef.current === highlightRunId) return
    const match = runs.find((run) => run.run_id === highlightRunId)
    if (match) {
      setExpandedRunId(highlightRunId)
      consumedHighlightRef.current = highlightRunId
      const params = new URLSearchParams(searchParamsString)
      params.delete("highlight")
      const query = params.toString()
      router.replace(query ? `${pathname}?${query}` : pathname)
    }
  }, [highlightRunId, pathname, router, runs, searchParamsString])

  useEffect(() => {
    setCursor(null)
    setCursorHistory([])
  }, [effectiveProjectId, scope, statusFilter])

  // Load details when a run is expanded
  useEffect(() => {
    if (!expandedRunId) {
      setLogs(null)
      setOutputs(null)
      setDag(null)
      return
    }
    const loadDetails = async () => {
      try {
        const [logsResponse, outputsResponse, dagResponse] = await Promise.all([
          apiRequest<RunLogs>(`/runs/${expandedRunId}/logs`, { params: { tail: 200 } }),
          apiRequest<RunOutputs>(`/runs/${expandedRunId}/outputs`),
          apiRequest<DagData>(`/runs/${expandedRunId}/dag`),
        ])
        setLogs(logsResponse.data)
        setOutputs(outputsResponse.data)
        setDag(dagResponse.data)
      } catch (error) {
        const message = getApiErrorMessage(error, tRuns("errors.loadRunDetailsFailed"))
        toast.error(message)
      }
    }
    loadDetails()
  }, [expandedRunId, tRuns])

  // Escape key collapses expanded row
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && expandedRunId) {
        setExpandedRunId(null)
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [expandedRunId])

  const getPipelineName = useCallback((run: Run) => {
    if (run.workflow_id && workflowNameMap.has(run.workflow_id)) {
      return workflowNameMap.get(run.workflow_id) as string
    }
    return run.workflow_id
      ? tRuns("workflowFallback", { id: run.workflow_id.slice(0, 8) })
      : tRuns("unknownWorkflow")
  }, [workflowNameMap, tRuns])

  const toggleExpand = useCallback((run: Run) => {
    setExpandedRunId((prev) => (prev === run.run_id ? null : run.run_id))
  }, [])

  const handleViewLogs = useCallback((run: Run) => {
    toast.info(tRuns("toasts.openingLogsTitle", { runId: run.run_id }), {
      description: tRuns("toasts.pipelineLabel", { pipeline: getPipelineName(run) }),
    })
    setExpandedRunId(run.run_id)
  }, [getPipelineName, tRuns])

  const handleResume = useCallback(async (run: Run) => {
    toast.info(tRuns("toasts.resumingTitle", { runId: run.run_id }), {
      description: tRuns("toasts.resumingDescription"),
    })
    try {
      await apiRequest(`/runs/${run.run_id}/resume`, { method: "POST" })
      toast.success(tRuns("toasts.resumedTitle", { runId: run.run_id }), {
        description: tRuns("toasts.executionQueued"),
      })
      fetchRuns()
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.resumeFailed"))
      toast.error(message)
    }
  }, [fetchRuns, tRuns])

  const handleRetry = useCallback(async (run: Run) => {
    toast.info(tRuns("toasts.retryingTitle", { runId: run.run_id }), {
      description: tRuns("toasts.retryingDescription"),
    })
    try {
      await apiRequest(`/runs/${run.run_id}/retry`, { method: "POST" })
      toast.success(tRuns("toasts.resubmittedTitle", { runId: run.run_id }), {
        description: tRuns("toasts.checkRunsPage"),
      })
      fetchRuns()
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.retryFailed"))
      toast.error(message)
    }
  }, [fetchRuns, tRuns])

  const executeCancel = useCallback(async (run: Run) => {
    try {
      const { data } = await apiRequest<Run>(`/runs/${run.run_id}/cancel`, { method: "POST" })
      setRuns((prev) => prev.map((item) => (item.run_id === run.run_id ? data : item)))
      toast.success(tRuns("toasts.cancelledTitle", { runId: run.run_id }), {
        description: tRuns("toasts.executionStopped"),
      })
    } catch (error) {
      const message = getApiErrorMessage(error, tRuns("errors.cancelFailed"))
      toast.error(message)
    }
  }, [tRuns])

  const handleDelete = useCallback((run: Run) => {
    toast.warning(tRuns("toasts.deleteConfirmTitle", { runId: run.run_id }), {
      description: tRuns("toasts.deleteConfirmDescription"),
      action: {
        label: tCommon("confirm"),
        onClick: async () => {
          try {
            await apiRequest(`/runs/${run.run_id}`, { method: "DELETE" })
            setRuns((prev) => prev.filter((item) => item.run_id !== run.run_id))
            toast.success(tRuns("toasts.deletedTitle", { runId: run.run_id }))
            if (expandedRunId === run.run_id) {
              setExpandedRunId(null)
            }
          } catch (error) {
            const message = getApiErrorMessage(error, tRuns("errors.deleteFailed"))
            toast.error(message)
          }
        },
      },
    })
  }, [expandedRunId, tCommon, tRuns])

  const handleDownloadResults = useCallback((run: Run) => {
    const url = buildApiUrl(`/runs/${run.run_id}/outputs/download`, { format: "tar.gz" })
    openInNewTab(url)
  }, [])

  const handleRerun = useCallback((run: Run) => {
    handleRetry(run)
    setExpandedRunId(null)
  }, [handleRetry])

  const handleCleanup = useCallback((run: Run) => {
    toast.warning(tRuns("toasts.cleanupConfirmTitle", { runId: run.run_id }), {
      description: tRuns("toasts.cleanupConfirmDescription"),
      action: {
        label: tCommon("confirm"),
        onClick: async () => {
          try {
            await apiRequest(`/runs/${run.run_id}/cleanup`, { method: "POST" })
            toast.success(tRuns("toasts.cleanupDoneTitle", { runId: run.run_id }))
          } catch (error) {
            const message = getApiErrorMessage(error, tRuns("errors.cleanupFailed"))
            toast.error(message)
          }
        },
      },
    })
  }, [tCommon, tRuns])

  const handleDownloadFile = useCallback((path: string) => {
    if (!expandedRunId) return
    const url = buildApiUrl(`/runs/${expandedRunId}/outputs/download`, { file: path, format: "tar.gz" })
    openInNewTab(url)
  }, [expandedRunId])

  const filteredRuns = runs.filter((run) => {
    const query = search.toLowerCase()
    const pipelineName = getPipelineName(run).toLowerCase()
    return run.run_id.toLowerCase().includes(query) || pipelineName.includes(query)
  })

  const expandedRun = expandedRunId ? runs.find((r) => r.run_id === expandedRunId) ?? null : null

  const handlePrevPage = useCallback(() => {
    if (!cursorHistory.length) return
    const previous = cursorHistory[cursorHistory.length - 1] ?? null
    setCursorHistory((prev) => prev.slice(0, -1))
    setCursor(previous)
  }, [cursorHistory])

  const handleNextPage = useCallback(() => {
    if (!pagination?.next_cursor) return
    setCursorHistory((prev) => [...prev, cursor])
    setCursor(pagination.next_cursor || null)
  }, [cursor, pagination])

  const handleSubmittedRun = useCallback(async (runId: string) => {
    const nextScope = effectiveProjectId ? "project" : scope
    const params = new URLSearchParams(searchParamsString)
    params.set("scope", nextScope)
    if (effectiveProjectId) {
      params.set("project_id", effectiveProjectId)
    }
    params.set("highlight", runId)
    router.replace(`${pathname}?${params.toString()}`)
    setCursor(null)
    setCursorHistory([])
    setExpandedRunId(runId)
    await fetchRuns(null)
  }, [effectiveProjectId, fetchRuns, pathname, router, scope, searchParamsString])

  return {
    tRuns,
    tStatus,
    tCommon,
    runs,
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
  }
}
