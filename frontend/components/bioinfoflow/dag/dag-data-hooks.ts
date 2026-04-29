import { useEffect, useState } from "react"
import { apiRequest } from "@/lib/api"
import type { DagData, ProjectWorkflowGroup, Run } from "@/lib/types"

/* ── runs loader ────────────────────────────────────────── */

export function useDagRuns(projectId: string | null | undefined, showRunSelect: boolean) {
  const [runs, setRuns] = useState<Run[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runsError, setRunsError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId || !showRunSelect) {
      setRuns([])
      return
    }

    let cancelled = false
    const loadRuns = async () => {
      setRunsLoading(true)
      setRunsError(null)
      try {
        const response = await apiRequest<Run[]>("/runs", {
          params: { project_id: projectId, limit: 50 },
        })
        if (!cancelled) {
          setRuns(response.data)
        }
      } catch {
        if (!cancelled) {
          setRunsError("Failed to load runs")
        }
      } finally {
        if (!cancelled) {
          setRunsLoading(false)
        }
      }
    }

    loadRuns()
    return () => {
      cancelled = true
    }
  }, [projectId, showRunSelect])

  return { runs, runsLoading, runsError }
}

/* ── workflow groups loader ─────────────────────────────── */

export function useDagWorkflowGroups(projectId: string | null | undefined) {
  const [workflowGroups, setWorkflowGroups] = useState<ProjectWorkflowGroup[]>([])
  const [selectedGroupIndex, setSelectedGroupIndex] = useState<number | null>(null)
  const [workflowGroupsLoading, setWorkflowGroupsLoading] = useState(false)

  useEffect(() => {
    if (!projectId) {
      setWorkflowGroups([])
      setSelectedGroupIndex(null)
      return
    }

    let cancelled = false
    const loadGroups = async () => {
      setWorkflowGroupsLoading(true)
      try {
        const response = await apiRequest<ProjectWorkflowGroup[]>(`/projects/${projectId}/workflows`)
        if (!cancelled) {
          setWorkflowGroups(response.data)
          setSelectedGroupIndex(response.data.length > 0 ? 0 : null)
        }
      } catch {
        if (!cancelled) {
          setWorkflowGroups([])
          setSelectedGroupIndex(null)
        }
      } finally {
        if (!cancelled) {
          setWorkflowGroupsLoading(false)
        }
      }
    }

    loadGroups()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const selectedGroup = selectedGroupIndex === null ? null : workflowGroups[selectedGroupIndex] ?? null

  return {
    workflowGroups,
    selectedGroupIndex,
    setSelectedGroupIndex,
    workflowGroupsLoading,
    selectedGroup,
  }
}

/* ── DAG data fetcher ───────────────────────────────────── */

export function useDagFetch(
  runId: string | null | undefined,
  effectiveWorkflowId: string | null,
  dag: DagData | null | undefined,
  applyDagData: (dagData: DagData) => void,
  clearGraph: () => void,
) {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (dag) {
      applyDagData(dag)
    }
  }, [applyDagData, dag])

  useEffect(() => {
    if (dag) return

    if (!runId && !effectiveWorkflowId) {
      setError(null)
      clearGraph()
      return
    }

    let cancelled = false
    const fetchDag = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const response = runId
          ? await apiRequest<DagData>(`/runs/${runId}/dag`)
          : await apiRequest<DagData>(`/workflows/${effectiveWorkflowId}/dag`)
        if (!cancelled) {
          applyDagData(response.data ?? { nodes: [], edges: [] })
        }
      } catch {
        if (!cancelled) {
          clearGraph()
          setError("Failed to load DAG")
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    fetchDag()
    return () => {
      cancelled = true
    }
  }, [applyDagData, clearGraph, dag, effectiveWorkflowId, runId])

  return { isLoading, error }
}
