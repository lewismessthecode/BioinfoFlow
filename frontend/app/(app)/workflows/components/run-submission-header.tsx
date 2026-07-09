"use client"

import { ArrowLeftRight, GitBranch, Workflow as WorkflowIcon, X } from "@/lib/icons"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { engineStyleFor } from "./workflow-pills"
import type { Workflow } from "@/lib/types"

interface RunSubmissionHeaderProps {
  workflow: Workflow
  onChangeWorkflow: () => void
  onClose: () => void
}

export function RunSubmissionHeader({
  workflow,
  onChangeWorkflow,
  onClose,
}: RunSubmissionHeaderProps) {
  const t = useTranslations("workflows.submission")
  const engine = engineStyleFor(workflow.engine)

  return (
    <header className="shrink-0 border-b border-border/60 bg-background/95 px-4 py-4 backdrop-blur sm:px-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              <WorkflowIcon className="h-3.5 w-3.5" />
              {t("workbench.badge")}
            </span>
            <span className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium ${engine.classes}`}>
              {engine.label}
            </span>
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <GitBranch className="h-3.5 w-3.5" />
              {workflow.version}
            </span>
          </div>
          <h2 className="mt-3 truncate text-xl font-semibold text-foreground">
            {workflow.name}
          </h2>
          {workflow.description && (
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              {workflow.description}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            className="hidden rounded-xl sm:inline-flex"
            onClick={onChangeWorkflow}
          >
            <ArrowLeftRight className="mr-2 h-4 w-4" />
            {t("workbench.changeWorkflow")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="rounded-xl"
            onClick={onClose}
            aria-label={t("workbench.closeAria")}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="mt-3 sm:hidden">
        <Button
          type="button"
          variant="outline"
          className="w-full rounded-xl"
          onClick={onChangeWorkflow}
        >
          <ArrowLeftRight className="mr-2 h-4 w-4" />
          {t("workbench.changeWorkflow")}
        </Button>
      </div>
    </header>
  )
}
