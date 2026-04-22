"use client"

import { startTransition, useCallback, useEffect, useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { apiRequest } from "@/lib/api"
import type { ProjectWorkflowGroup, Workflow } from "@/lib/types"
import { RunSubmissionWorkbench } from "./run-submission-workbench"
import { WorkflowPickerDialog } from "./workflow-picker-dialog"

interface RunSubmissionWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  projectId: string
  initialWorkflowId?: string | null
  availableWorkflows?: Workflow[]
  onSubmitted?: (runId: string) => void
}

export function RunSubmissionWizard({
  open,
  onOpenChange,
  projectId,
  initialWorkflowId,
  availableWorkflows,
  onSubmitted,
}: RunSubmissionWizardProps) {
  const t = useTranslations("workflows.submission")
  const [fetchedWorkflows, setFetchedWorkflows] = useState<Workflow[]>([])
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string | null>(
    initialWorkflowId ?? null,
  )
  const [pickerWorkflowId, setPickerWorkflowId] = useState<string | null>(
    initialWorkflowId ?? null,
  )
  const workflows = availableWorkflows ?? fetchedWorkflows

  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === selectedWorkflowId) ?? null,
    [selectedWorkflowId, workflows],
  )
  const pickerWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === pickerWorkflowId) ?? null,
    [pickerWorkflowId, workflows],
  )

  const fetchWorkflows = useCallback(async () => {
    if (!open || availableWorkflows || !projectId) return
    const { data } = await apiRequest<ProjectWorkflowGroup[]>(`/projects/${projectId}/workflows`)
    return data.map((group) => group.pinned_workflow)
  }, [availableWorkflows, open, projectId])

  useEffect(() => {
    if (!open || availableWorkflows) return
    let isCancelled = false

    const loadWorkflows = async () => {
      try {
        const nextWorkflows = await fetchWorkflows()
        if (!isCancelled && nextWorkflows) {
          setFetchedWorkflows(nextWorkflows)
        }
      } catch {
        if (!isCancelled) {
          toast.error(t("errors.loadWorkflowsFailed"))
        }
      }
    }

    void loadWorkflows()

    return () => {
      isCancelled = true
    }
  }, [availableWorkflows, fetchWorkflows, open, t])

  useEffect(() => {
    if (!open) return
    // We intentionally re-seed the local drafts each time the dialog opens so
    // the picker and workbench reflect the workflow chosen by the caller.
    startTransition(() => {
      setSelectedWorkflowId(initialWorkflowId ?? null)
      setPickerWorkflowId(initialWorkflowId ?? null)
    })
  }, [initialWorkflowId, open])

  const handleClose = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        startTransition(() => {
          setSelectedWorkflowId(initialWorkflowId ?? null)
          setPickerWorkflowId(initialWorkflowId ?? null)
        })
      }
      onOpenChange(nextOpen)
    },
    [initialWorkflowId, onOpenChange],
  )

  const handleWorkflowChange = useCallback((workflowId: string | null) => {
    startTransition(() => {
      setPickerWorkflowId(workflowId)
      setSelectedWorkflowId(null)
    })
  }, [])

  const handleWorkflowConfirm = useCallback(() => {
    if (!pickerWorkflowId) return
    startTransition(() => {
      setSelectedWorkflowId(pickerWorkflowId)
    })
  }, [pickerWorkflowId])

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        showCloseButton={false}
        className="inset-0 left-0 top-0 flex h-screen w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none border-0 p-0 sm:inset-auto sm:left-[50%] sm:top-[50%] sm:h-[min(88vh,860px)] sm:w-[min(960px,calc(100vw-3rem))] sm:max-w-none sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-[28px] sm:border"
      >
        <DialogTitle className="sr-only">{t("title")}</DialogTitle>
        <DialogDescription className="sr-only">{t("description")}</DialogDescription>

        <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
          {selectedWorkflow ? (
            <RunSubmissionWorkbench
              key={selectedWorkflow.id}
              workflow={selectedWorkflow}
              projectId={projectId}
              onClose={() => handleClose(false)}
              onChangeWorkflow={() => handleWorkflowChange(selectedWorkflow.id)}
              onSubmitted={(runId) => {
                onSubmitted?.(runId)
                handleClose(false)
              }}
            />
          ) : (
            <WorkflowPickerDialog
              workflows={workflows}
              selectedWorkflow={pickerWorkflow}
              onClose={() => handleClose(false)}
              onSelectWorkflow={(workflow) => setPickerWorkflowId(workflow.id)}
              onConfirm={handleWorkflowConfirm}
            />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
