"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import dynamic from "next/dynamic"
import { useTranslations } from "next-intl"
import {
  Plus,
  Search,
  GitBranch,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { EmptyState } from "@/components/ui/empty-state"
import { ViewToggle, type ViewMode } from "@/components/ui/view-toggle"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import type { HubWorkflowGroup, ProjectWorkflowGroup, Workflow } from "@/lib/types"
import { WorkflowsGridSkeleton, WorkflowsTableSkeleton } from "./components/workflows-skeleton"
import { HubWorkflowCard } from "./components/hub-workflow-card"
import { ProjectGroupCard } from "./components/project-group-card"
import { HubWorkflowsTable, ProjectWorkflowsTable } from "./components/workflow-table-views"
import { useWorkflowActions } from "./components/use-workflow-actions"
import { buildHubWorkflowGroups } from "@/lib/workflow-groups"

const WorkflowRegisterDialog = dynamic(
  () => import("./components/workflow-register-dialog").then((m) => ({ default: m.WorkflowRegisterDialog })),
  { ssr: false },
)
const RunSubmissionWizard = dynamic(
  () => import("./components/run-submission-wizard").then((m) => ({ default: m.RunSubmissionWizard })),
  { ssr: false },
)

function resolveWorkflowScope(scopeParam: string | null, projectId: string): "project" | "hub" {
  if (scopeParam === "hub") return "hub"
  if (scopeParam === "project") return projectId ? "project" : "hub"
  return projectId ? "project" : "hub"
}

export default function WorkflowsPage() {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const urlScope = searchParams.get("scope")
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")
  const { activeProjectId } = useProjectContext()
  const [scope, setScope] = useState<"project" | "hub">(() =>
    resolveWorkflowScope(urlScope, activeProjectId)
  )
  const [hubWorkflows, setHubWorkflows] = useState<Workflow[]>([])
  const [projectWorkflows, setProjectWorkflows] = useState<ProjectWorkflowGroup[]>([])
  const [view, setView] = useState<ViewMode>("cards")
  const [search, setSearch] = useState("")
  const [registerOpen, setRegisterOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [runOpen, setRunOpen] = useState(false)
  const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null)

  const fetchHubWorkflows = useCallback(async () => {
    const { data } = await apiRequest<Workflow[]>("/workflows", { params: { limit: 200 } })
    setHubWorkflows(data)
  }, [])

  const fetchProjectWorkflows = useCallback(async () => {
    if (!activeProjectId) return
    const { data } = await apiRequest<ProjectWorkflowGroup[]>(
      `/projects/${activeProjectId}/workflows`
    )
    setProjectWorkflows(data)
  }, [activeProjectId])

  useEffect(() => {
    const resolvedScope = resolveWorkflowScope(urlScope, activeProjectId)
    setScope(resolvedScope)
    if (!activeProjectId) setProjectWorkflows([])
  }, [activeProjectId, urlScope])

  const updateScopeUrl = useCallback((nextScope: "project" | "hub") => {
    const params = new URLSearchParams(searchParams.toString())
    params.set("scope", nextScope)
    const query = params.toString()
    router.replace(query ? `${pathname}?${query}` : pathname)
  }, [pathname, router, searchParams])

  const handleScopeChange = useCallback((nextScope: "project" | "hub") => {
    const resolvedScope = nextScope === "project" && activeProjectId ? "project" : "hub"
    setScope(resolvedScope)
    updateScopeUrl(resolvedScope)
  }, [activeProjectId, updateScopeUrl])

  useEffect(() => {
    const load = async () => {
      setIsLoading(true)
      try {
        const minLoadTime = new Promise((resolve) => setTimeout(resolve, 500))
        if (scope === "hub") {
          await Promise.all([fetchHubWorkflows(), minLoadTime])
        } else if (!activeProjectId) {
          setProjectWorkflows([])
          await minLoadTime
        } else {
          await Promise.all([fetchProjectWorkflows(), minLoadTime])
        }
      } catch (error) {
        toast.error(getApiErrorMessage(error, tWorkflows("errors.loadWorkflowsFailed")))
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [scope, activeProjectId, fetchHubWorkflows, fetchProjectWorkflows, tWorkflows])

  const actions = useWorkflowActions({
    activeProjectId,
    scope,
    setHubWorkflows,
    fetchProjectWorkflows,
    setSelectedWorkflow,
    setRunOpen,
  })

  const filteredHubWorkflows = useMemo(() => {
    const query = search.toLowerCase()
    const grouped = buildHubWorkflowGroups(hubWorkflows)

    return grouped.filter((group) => {
      if (!query) return true
      return group.versions.some((workflow) =>
        workflow.name.toLowerCase().includes(query) ||
        (workflow.description?.toLowerCase().includes(query) ?? false) ||
        workflow.version.toLowerCase().includes(query),
      )
    })
  }, [hubWorkflows, search])

  const projectScopedWizardWorkflows = useMemo(
    () => projectWorkflows.map((group) => group.pinned_workflow),
    [projectWorkflows],
  )

  const filteredProjectGroups = useMemo(() => {
    const query = search.toLowerCase()
    return projectWorkflows.filter((group) => {
      const wf = group.pinned_workflow
      return wf.name.toLowerCase().includes(query) ||
        (wf.description?.toLowerCase().includes(query) ?? false)
    })
  }, [projectWorkflows, search])

  const hasFilteredHubGroups = filteredHubWorkflows.length > 0
  const hasFilteredProjectGroups = filteredProjectGroups.length > 0

  const renderHubCards = (groups: HubWorkflowGroup[]) =>
    groups.map((group) => (
      <HubWorkflowCard
        key={`${group.source}:${group.engine}:${group.name}`}
        group={group}
        formatWorkflowName={actions.formatWorkflowName}
        activeProjectId={activeProjectId}
        onBind={actions.handleBind}
        onViewDetails={actions.handleViewDetails}
        onEditParameters={actions.handleEditParameters}
        onDuplicate={actions.handleDuplicate}
        onDelete={actions.handleDelete}
      />
    ))

  const renderProjectCards = () =>
    filteredProjectGroups.map((group) => (
      <ProjectGroupCard
        key={`${group.source}:${group.name}`}
        group={group}
        formatWorkflowName={actions.formatWorkflowName}
        onRun={actions.handleRun}
        onViewDetails={actions.handleViewDetails}
        onUnbindGroup={actions.handleUnbindGroup}
        onSetPinnedVersion={actions.handleSetPinnedVersion}
      />
    ))

  return (
    <div className="h-full overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-foreground">{tWorkflows("title")}</h1>
              <Badge variant="secondary" className="text-xs">
                {scope === "hub" ? tWorkflows("scopes.hub") : tWorkflows("scopes.project")}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">{tWorkflows("subtitle")}</p>
          </div>
          {scope === "hub" && (
            <>
              <Button onClick={() => setRegisterOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                {tWorkflows("register")}
              </Button>
              <WorkflowRegisterDialog
                open={registerOpen}
                onOpenChange={setRegisterOpen}
                onRegistered={(wf) => setHubWorkflows((prev) => [wf, ...prev])}
              />
            </>
          )}
        </div>

        {/* Actions Bar */}
        <div className="flex items-center justify-between gap-2 sm:gap-4 mb-5">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              id="workflow-search"
              placeholder={`${tCommon("search")}...`}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
            <Label htmlFor="workflow-search" className="sr-only">
              {tCommon("search")} {tWorkflows("title")}
            </Label>
          </div>
          <div className="flex items-center gap-2">
            <Tabs value={scope} onValueChange={(v) => handleScopeChange(v as "project" | "hub")}>
              <TabsList>
                <TabsTrigger value="project" disabled={!activeProjectId}>{tWorkflows("scopes.project")}</TabsTrigger>
                <TabsTrigger value="hub">{tWorkflows("scopes.hub")}</TabsTrigger>
              </TabsList>
            </Tabs>
            <RunSubmissionWizard
              open={runOpen}
              onOpenChange={(open) => { setRunOpen(open); if (!open) setSelectedWorkflow(null) }}
              projectId={activeProjectId}
              initialWorkflowId={selectedWorkflow?.id ?? null}
              availableWorkflows={scope === "project" ? projectScopedWizardWorkflows : undefined}
              onSubmitted={(runId) => {
                const params = new URLSearchParams()
                params.set("highlight", runId)
                params.set("scope", activeProjectId ? "project" : "hub")
                if (activeProjectId) {
                  params.set("project_id", activeProjectId)
                }
                router.push(`/runs?${params.toString()}`)
              }}
            />
            <ViewToggle view={view} onViewChange={setView} listLabel={tWorkflows("viewModes.list")} cardsLabel={tWorkflows("viewModes.cards")} />
          </div>
        </div>

        {/* Content */}
        {isLoading ? (
          view === "cards" ? <WorkflowsGridSkeleton /> : <WorkflowsTableSkeleton />
        ) : scope === "hub" && !hasFilteredHubGroups ? (
          <EmptyState icon={GitBranch} title={tWorkflows("noWorkflows")} description={tWorkflows("noWorkflowsDescription")} action={{ label: tWorkflows("register"), onClick: () => setRegisterOpen(true) }} />
        ) : scope === "project" && !hasFilteredProjectGroups ? (
          <EmptyState icon={GitBranch} title={tWorkflows("emptyProject")} description={tWorkflows("emptyProjectDescription")} />
        ) : (
          <>
            {view === "cards" ? (
              <div key={scope} className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 animate-in fade-in slide-in-from-bottom-4 zoom-in-95 duration-300 ease-apple-ease">
                {scope === "hub"
                  ? renderHubCards(filteredHubWorkflows)
                  : renderProjectCards()}
              </div>
            ) : (
              <div className="border border-border rounded-lg overflow-hidden">
                <table className="w-full">
                  <caption className="sr-only">{tWorkflows("tableCaption")}</caption>
                  <thead>
                    <tr className="border-b border-border bg-secondary/50">
                      <th scope="col" className="text-left text-xs font-medium text-muted-foreground px-4 py-3">{tWorkflows("name")}</th>
                      <th scope="col" className="text-left text-xs font-medium text-muted-foreground px-4 py-3">{tWorkflows("source")}</th>
                      <th scope="col" className="text-left text-xs font-medium text-muted-foreground px-4 py-3">{tWorkflows("engine")}</th>
                      <th scope="col" className="text-left text-xs font-medium text-muted-foreground px-4 py-3">{tWorkflows("version")}</th>
                      <th scope="col" className="text-left text-xs font-medium text-muted-foreground px-4 py-3">{tWorkflows("lastModified")}</th>
                      <th scope="col" className="text-right text-xs font-medium text-muted-foreground px-4 py-3">{tCommon("actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scope === "hub" ? (
                      <HubWorkflowsTable groups={filteredHubWorkflows} activeProjectId={activeProjectId} tWorkflows={tWorkflows} tCommon={tCommon} formatWorkflowName={actions.formatWorkflowName} onBind={actions.handleBind} onAddAndRun={actions.handleAddAndRun} onViewDetails={actions.handleViewDetails} onEditParameters={actions.handleEditParameters} onDuplicate={actions.handleDuplicate} onDelete={actions.handleDelete} />
                    ) : (
                      <ProjectWorkflowsTable groups={filteredProjectGroups} tWorkflows={tWorkflows} formatWorkflowName={actions.formatWorkflowName} onRun={actions.handleRun} onUnbindGroup={actions.handleUnbindGroup} onSetPinnedVersion={actions.handleSetPinnedVersion} />
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
