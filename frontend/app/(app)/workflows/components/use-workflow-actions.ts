import { useCallback } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import { celebrateMilestone } from "@/lib/celebrations"
import type { ProjectWorkflowGroup, Workflow } from "@/lib/types"

export function useWorkflowActions({
  activeProjectId,
  scope,
  setHubWorkflows,
  fetchProjectWorkflows,
  setSelectedWorkflow,
  setRunOpen,
}: {
  activeProjectId: string
  scope: "project" | "hub"
  setHubWorkflows: React.Dispatch<React.SetStateAction<Workflow[]>>
  fetchProjectWorkflows: () => Promise<void>
  setSelectedWorkflow: (wf: Workflow | null) => void
  setRunOpen: (open: boolean) => void
}) {
  const router = useRouter()
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")

  const formatWorkflowName = useCallback((workflow: Workflow) => {
    if (workflow.source === "nf-core" && !workflow.name.startsWith("nf-core/")) {
      return `nf-core/${workflow.name}`
    }
    return workflow.name
  }, [])

  const handleRun = useCallback((workflow: Workflow) => {
    if (!activeProjectId) {
      toast.error(tWorkflows("errors.selectProjectToRun"))
      return
    }
    setSelectedWorkflow(workflow)
    setRunOpen(true)
  }, [activeProjectId, tWorkflows, setSelectedWorkflow, setRunOpen])

  const handleBind = useCallback(async (workflow: Workflow) => {
    if (!activeProjectId) {
      toast.error(tWorkflows("errors.selectProjectFirst"))
      return false
    }
    try {
      await apiRequest(`/projects/${activeProjectId}/workflows/${workflow.id}:bind`, { method: "POST" })
      toast.success(tWorkflows("toasts.addedToProject", { name: formatWorkflowName(workflow) }))
      celebrateMilestone("first-workflow-bound")
      if (scope === "project") {
        await fetchProjectWorkflows()
      }
      return true
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkflows("errors.addToProjectFailed"))
      toast.error(message)
      return false
    }
  }, [activeProjectId, scope, tWorkflows, formatWorkflowName, fetchProjectWorkflows])

  const handleAddAndRun = useCallback(async (workflow: Workflow) => {
    if (!activeProjectId) {
      toast.error(tWorkflows("errors.selectProjectFirst"))
      return
    }
    const bindSucceeded = await handleBind(workflow)
    if (!bindSucceeded) return
    setSelectedWorkflow(workflow)
    setRunOpen(true)
  }, [activeProjectId, tWorkflows, handleBind, setSelectedWorkflow, setRunOpen])

  const handleUnbindGroup = useCallback(async (group: ProjectWorkflowGroup) => {
    if (!activeProjectId) return
    try {
      await Promise.all(
        group.versions.map((wf) =>
          apiRequest(`/projects/${activeProjectId}/workflows/${wf.id}:unbind`, { method: "DELETE" })
        )
      )
      toast.success(tWorkflows("toasts.removedFromProject", { name: formatWorkflowName(group.pinned_workflow) }))
      fetchProjectWorkflows()
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkflows("errors.removeFromProjectFailed"))
      toast.error(message)
    }
  }, [activeProjectId, tWorkflows, formatWorkflowName, fetchProjectWorkflows])

  const handleSetPinnedVersion = useCallback(async (workflowId: string) => {
    if (!activeProjectId) return
    try {
      await apiRequest(`/projects/${activeProjectId}/workflow-pins`, {
        method: "POST",
        body: JSON.stringify({ pinned_workflow_id: workflowId }),
      })
      await fetchProjectWorkflows()
    } catch (error) {
      const message = getApiErrorMessage(error, tWorkflows("errors.switchVersionFailed"))
      toast.error(message)
    }
  }, [activeProjectId, tWorkflows, fetchProjectWorkflows])

  const handleViewDetails = useCallback((workflow: Workflow) => {
    router.push(`/workflows/${workflow.id}`)
  }, [router])

  const handleEditParameters = useCallback((workflow: Workflow) => {
    toast.info(tWorkflows("toasts.parameterEditorTitle"), {
      description: tWorkflows("toasts.parameterEditorDescription", { name: workflow.name }),
    })
  }, [tWorkflows])

  const handleDuplicate = useCallback((workflow: Workflow) => {
    toast.success(tCommon("duplicate"), {
      description: tWorkflows("toasts.duplicatedDescription", { name: workflow.name }),
    })
  }, [tCommon, tWorkflows])

  const handleDelete = useCallback((workflow: Workflow) => {
    toast.warning(tWorkflows("toasts.deleteConfirmTitle", { name: workflow.name }), {
      description: tWorkflows("toasts.deleteConfirmDescription"),
      action: {
        label: tCommon("confirm"),
        onClick: async () => {
          try {
            await apiRequest(`/workflows/${workflow.id}`, { method: "DELETE" })
            setHubWorkflows((prev) => prev.filter((item) => item.id !== workflow.id))
            toast.success(tWorkflows("toasts.deleted", { name: workflow.name }))
          } catch (error) {
            const message = getApiErrorMessage(error, tWorkflows("errors.deleteFailed"))
            toast.error(message)
          }
        },
      },
    })
  }, [tCommon, tWorkflows, setHubWorkflows])

  return {
    formatWorkflowName,
    handleRun,
    handleBind,
    handleAddAndRun,
    handleUnbindGroup,
    handleSetPinnedVersion,
    handleViewDetails,
    handleEditParameters,
    handleDuplicate,
    handleDelete,
  }
}
