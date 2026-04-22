"use client"

import { ArrowRight, Sparkles } from "lucide-react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import type { Workflow } from "@/lib/types"
import { StepWorkflowSelect } from "./wizard/step-workflow-select"

interface WorkflowPickerDialogProps {
  workflows: Workflow[]
  selectedWorkflow: Workflow | null
  onClose: () => void
  onSelectWorkflow: (workflow: Workflow) => void
  onConfirm: () => void
}

export function WorkflowPickerDialog({
  workflows,
  selectedWorkflow,
  onClose,
  onSelectWorkflow,
  onConfirm,
}: WorkflowPickerDialogProps) {
  const t = useTranslations("workflows.submission")

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0 border-b border-border/60 bg-background/95 px-4 py-5 sm:px-6">
        <div className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" />
          {t("workbench.badge")}
        </div>
        <h2 className="mt-3 text-xl font-semibold text-foreground">
          {t("workbench.pickerTitle")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("workbench.pickerDescription")}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-4 py-4 sm:px-6">
        <StepWorkflowSelect
          workflows={workflows}
          selectedWorkflow={selectedWorkflow}
          onSelect={onSelectWorkflow}
        />
      </div>

      <div className="shrink-0 border-t border-border/60 bg-background/95 px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" className="rounded-xl" onClick={onClose}>
            {t("workbench.cancel")}
          </Button>
          <Button
            type="button"
            className="rounded-xl"
            onClick={onConfirm}
            disabled={!selectedWorkflow}
          >
            {t("workbench.continue")}
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
