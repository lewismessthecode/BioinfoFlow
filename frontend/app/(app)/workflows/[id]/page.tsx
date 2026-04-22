"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import {
  ArrowLeft,
  Clock,
  GitBranch,
  Settings,
  ExternalLink,
  Copy,
  FileCode,
  List,
  Network,
  Info,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { Workflow, DagData, WorkflowSchema } from "@/lib/types"
import WorkflowDetailLoading from "./loading"
import { WorkflowOverviewTab } from "./components/workflow-overview-tab"
import { WorkflowParametersTab } from "./components/workflow-parameters-tab"
import { WorkflowTasksTab } from "./components/workflow-tasks-tab"
import { WorkflowSourceTab } from "./components/workflow-source-tab"
import { DagPanel } from "@/components/bioinfoflow/dag"
import { useViewportFitHeight } from "@/hooks/use-viewport-fit-height"
import { useSetBreadcrumbDetail } from "@/hooks/use-set-breadcrumb-detail"

export default function WorkflowDetailPage() {
  const params = useParams()
  const router = useRouter()
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")
  const workflowId = params.id as string
  const { ref: dagFrameRef, style: dagFrameStyle } = useViewportFitHeight<HTMLDivElement>()

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [compareCandidates, setCompareCandidates] = useState<Workflow[]>([])
  const [selectedCompareWorkflowId, setSelectedCompareWorkflowId] = useState<string | null>(null)
  const [compareSource, setCompareSource] = useState<string | null>(null)
  const [isCompareLoading, setIsCompareLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [activeTab, setActiveTab] = useState("overview")

  useSetBreadcrumbDetail(workflow?.name)

  const fetchWorkflow = useCallback(async () => {
    try {
      const { data } = await apiRequest<Workflow>(`/workflows/${workflowId}`)
      setWorkflow(data)
      return data
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkflows("errors.loadWorkflowFailed"))
      toast.error(message)
      return null
    }
  }, [workflowId, tWorkflows])

  const fetchDag = useCallback(async () => {
    try {
      const { data } = await apiRequest<DagData>(`/workflows/${workflowId}/dag`)
      setDag(data)
    } catch {
      // DAG might not be available, that's ok
    }
  }, [workflowId])

  const fetchSource = useCallback(async () => {
    // Only fetch source for local workflows
    if (workflow.source !== "local") return

    try {
      const { data } = await apiRequest<{ content: string }>(`/workflows/${workflowId}/source`)
      setSource(data.content)
    } catch {
      // Source might not be available
    }
  }, [workflow, workflowId])

  const fetchCompareCandidates = useCallback(async () => {
    if (!workflow || workflow.source !== "local") {
      setCompareCandidates([])
      return
    }

    try {
      const { data } = await apiRequest<Workflow[]>("/workflows", {
        params: { limit: 200 },
      })
      const candidates = data
        .filter((item) =>
          item.id !== workflow.id
          && item.source === workflow.source
          && item.engine === workflow.engine
          && item.name === workflow.name,
        )
        .sort((left, right) =>
          right.version.localeCompare(left.version, undefined, {
            numeric: true,
            sensitivity: "base",
          }),
        )
      setCompareCandidates(candidates)
    } catch {
      setCompareCandidates([])
    }
  }, [workflow])

  const fetchCompareSource = useCallback(async (compareWorkflowId: string | null) => {
    if (!compareWorkflowId) {
      setCompareSource(null)
      setIsCompareLoading(false)
      return
    }

    setIsCompareLoading(true)
    try {
      const { data } = await apiRequest<{ content: string }>(`/workflows/${compareWorkflowId}/source`)
      setCompareSource(data.content)
    } catch {
      setCompareSource(null)
    } finally {
      setIsCompareLoading(false)
    }
  }, [])

  useEffect(() => {
    const load = async () => {
      setIsLoading(true)
      await Promise.all([fetchWorkflow(), fetchDag()])
      setIsLoading(false)
    }
    load()
  }, [fetchDag, fetchWorkflow])

  useEffect(() => {
    setSource(null)
    setCompareCandidates([])
    setSelectedCompareWorkflowId(null)
    setCompareSource(null)
    setIsCompareLoading(false)
  }, [workflowId])

  useEffect(() => {
    setSelectedCompareWorkflowId(null)
    setCompareSource(null)
    setIsCompareLoading(false)
  }, [workflow?.id])

  useEffect(() => {
    void fetchCompareSource(selectedCompareWorkflowId)
  }, [fetchCompareSource, selectedCompareWorkflowId])

  const handleTabChange = useCallback(
    (tab: string) => {
      setActiveTab(tab)
      if (tab === "source") {
        void fetchSource()
        void fetchCompareCandidates()
      }
    },
    [fetchCompareCandidates, fetchSource]
  )

  const formatWorkflowName = (wf: Workflow) => {
    if (wf.source === "nf-core" && !wf.name.startsWith("nf-core/")) {
      return `nf-core/${wf.name}`
    }
    return wf.name
  }

  const handleCopyId = () => {
    navigator.clipboard.writeText(workflowId)
    toast.success(tWorkflows("detail.toasts.copiedId"))
  }

  if (isLoading) {
    return <WorkflowDetailLoading />
  }

  if (!workflow) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-lg font-semibold text-foreground mb-2">{tWorkflows("detail.notFound.title")}</h2>
          <p className="text-sm text-muted-foreground mb-4">{tWorkflows("detail.notFound.description")}</p>
          <Button variant="outline" onClick={() => router.push("/workflows")}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            {tWorkflows("detail.backToWorkflows")}
          </Button>
        </div>
      </div>
    )
  }

  const schema = workflow.schema_json as WorkflowSchema | null
  const readinessTaskCount = schema?.tasks?.length ?? 0
  const readinessDependencyCount = dag?.edges?.length ?? schema?.dependencies?.length ?? 0
  const sourceRef = workflow.source_ref ?? workflow.entrypoint_relpath ?? null
  const sourceRefIsHttp = sourceRef?.startsWith("http") ?? false
  const readinessBadges = [workflow.engine.toUpperCase()]

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="sm"
          className="mb-4 -ml-2 text-muted-foreground hover:text-foreground"
          onClick={() => router.push("/workflows")}
        >
          <ArrowLeft className="h-4 w-4 mr-1" />
          {tCommon("back")}
        </Button>

        {/* Header */}
        <div className="mb-6">
          <div className="flex items-start gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-gradient-to-br from-secondary/70 via-background to-background shadow-sm">
              <svg viewBox="0 0 24 24" className="h-6 w-6 text-foreground/80" fill="currentColor">
                <path d="M12 2L2 7v10l10 5 10-5V7L12 2zm0 2.18l6.9 3.45L12 11.09 5.1 7.63 12 4.18zM4 16.54V9.09l7 3.5v7.45l-7-3.5zm9 3.5v-7.45l7-3.5v7.45l-7 3.5z" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-1">
                <h1 className="text-2xl font-semibold text-foreground truncate">
                  {formatWorkflowName(workflow)}
                </h1>
                <Badge variant="secondary" className="text-xs-tight uppercase tracking-wide shrink-0">
                  {workflow.source}
                </Badge>
                {readinessBadges.map((badge) => (
                  <Badge key={badge} variant="outline" className="text-xs-tight uppercase tracking-wide shrink-0">
                    {badge}
                  </Badge>
                ))}
              </div>
              <p className="text-sm text-muted-foreground">
                {workflow.description || tWorkflows("detail.noDescription")}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={handleCopyId}
              title={tWorkflows("detail.copyId")}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Readiness Bar */}
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-border/60 bg-card/50 px-4 py-3">
          <div className="flex items-center gap-2 text-sm">
            <span className={`inline-block h-2 w-2 rounded-full ${readinessTaskCount > 0 ? "bg-success" : "bg-muted-foreground/30"}`} />
            <span className="text-foreground/85">
              {tWorkflows("detail.readiness.tasksCompact", { count: readinessTaskCount })}
            </span>
          </div>
          <div className="h-4 w-px bg-border" />
          <div className="flex items-center gap-2 text-sm">
            <span className={`inline-block h-2 w-2 rounded-full ${readinessDependencyCount > 0 ? "bg-success" : "bg-muted-foreground/30"}`} />
            <span className="text-foreground/85">
              {tWorkflows("detail.readiness.dependenciesCompact", { count: readinessDependencyCount })}
            </span>
          </div>
          <div className="h-4 w-px bg-border" />
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-block h-2 w-2 rounded-full bg-warning" />
            <span className="text-foreground/85">
              {tWorkflows("detail.readiness.runtimeAssetsCompact")}
            </span>
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="p-4 rounded-lg border border-border/60 bg-card/50">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <Settings className="h-3 w-3" />
              {tWorkflows("engine")}
            </div>
            <p className="text-sm font-medium text-foreground capitalize">{workflow.engine}</p>
          </div>
          <div className="p-4 rounded-lg border border-border/60 bg-card/50">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <GitBranch className="h-3 w-3" />
              {tWorkflows("version")}
            </div>
            <p className="text-sm font-medium text-foreground font-mono">{workflow.version}</p>
          </div>
          <div className="p-4 rounded-lg border border-border/60 bg-card/50">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <Clock className="h-3 w-3" />
              {tWorkflows("detail.estTime")}
            </div>
            <p className="text-sm font-medium text-foreground">{workflow.estimated_time || "—"}</p>
          </div>
          <div className="p-4 rounded-lg border border-border/60 bg-card/50">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <ExternalLink className="h-3 w-3" />
              {tWorkflows("detail.sourceUrl")}
            </div>
            {sourceRef ? (
              sourceRefIsHttp ? (
                <a
                  href={sourceRef}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-foreground truncate block hover:text-primary transition-colors"
                >
                  {sourceRef.length > 30 ? `${sourceRef.slice(0, 30)}...` : sourceRef}
                </a>
              ) : (
                <p className="text-sm font-medium text-foreground break-all">{sourceRef}</p>
              )
            ) : (
              <p className="text-sm font-medium text-foreground">—</p>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
          <TabsList className="mb-4">
            <TabsTrigger value="overview" className="gap-2">
              <Info className="h-4 w-4" />
              {tWorkflows("detail.tabs.overview")}
            </TabsTrigger>
            <TabsTrigger value="parameters" className="gap-2">
              <List className="h-4 w-4" />
              {tWorkflows("detail.tabs.parameters")}
            </TabsTrigger>
            <TabsTrigger value="tasks" className="gap-2">
              <Settings className="h-4 w-4" />
              {tWorkflows("detail.tabs.tasks")}
            </TabsTrigger>
            <TabsTrigger value="dag" className="gap-2">
              <Network className="h-4 w-4" />
              {tWorkflows("detail.tabs.dag")}
            </TabsTrigger>
            <TabsTrigger value="source" className="gap-2">
              <FileCode className="h-4 w-4" />
              {tWorkflows("detail.tabs.source")}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-0">
            <WorkflowOverviewTab workflow={workflow} schema={schema} />
          </TabsContent>

          <TabsContent value="parameters" className="mt-0">
            <WorkflowParametersTab schema={schema} />
          </TabsContent>

          <TabsContent value="tasks" className="mt-0">
            <WorkflowTasksTab schema={schema} />
          </TabsContent>

          <TabsContent value="dag" className="mt-0">
            <div
              ref={dagFrameRef}
              style={dagFrameStyle}
              className="border border-border rounded-lg overflow-hidden"
            >
              <DagPanel workflowId={workflowId} dag={dag} variant="embedded" showHeader={false} />
            </div>
          </TabsContent>

          <TabsContent value="source" className="mt-0">
            <WorkflowSourceTab
              source={source}
              sourceRef={workflow.source_ref ?? workflow.entrypoint_relpath}
              workflowSource={workflow.source}
              engine={workflow.engine}
              currentVersion={workflow.version}
              compareCandidates={compareCandidates}
              selectedCompareWorkflowId={selectedCompareWorkflowId}
              compareSource={compareSource}
              isCompareLoading={isCompareLoading}
              onCompareWorkflowChange={setSelectedCompareWorkflowId}
            />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
