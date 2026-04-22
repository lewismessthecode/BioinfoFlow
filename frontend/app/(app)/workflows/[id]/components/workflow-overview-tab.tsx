"use client"

import { useTranslations } from "next-intl"
import { Badge } from "@/components/ui/badge"
import type { Workflow, WorkflowSchema } from "@/lib/types"

interface WorkflowOverviewTabProps {
  workflow: Workflow
  schema: WorkflowSchema | null
}

export function WorkflowOverviewTab({ workflow, schema }: WorkflowOverviewTabProps) {
  const tWorkflows = useTranslations("workflows")

  return (
    <div className="border border-border rounded-lg p-6 space-y-6">
      <div>
        <h3 className="text-sm font-medium text-foreground mb-2">{tWorkflows("detail.overview.description")}</h3>
        <p className="text-sm text-muted-foreground">
          {schema?.description || workflow.description || tWorkflows("detail.noDescription")}
        </p>
      </div>

      {/* Schema Info */}
      {schema && (
        <>
          {/* Workflow Name from Schema */}
          {schema.workflow_name && (
            <div>
              <h3 className="text-sm font-medium text-foreground mb-2">{tWorkflows("detail.overview.workflowName")}</h3>
              <p className="text-sm text-muted-foreground font-mono">{schema.workflow_name}</p>
            </div>
          )}

          {/* Version from Schema */}
          {schema.version && (
            <div>
              <h3 className="text-sm font-medium text-foreground mb-2">{tWorkflows("detail.overview.schemaVersion")}</h3>
              <Badge variant="outline">{schema.version}</Badge>
            </div>
          )}

          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-4 bg-secondary/30 rounded-lg">
              <p className="text-2xl font-semibold text-foreground">{schema.inputs?.length || 0}</p>
              <p className="text-xs text-muted-foreground">{tWorkflows("detail.overview.inputs")}</p>
            </div>
            <div className="text-center p-4 bg-secondary/30 rounded-lg">
              <p className="text-2xl font-semibold text-foreground">{schema.outputs?.length || 0}</p>
              <p className="text-xs text-muted-foreground">{tWorkflows("detail.overview.outputs")}</p>
            </div>
            <div className="text-center p-4 bg-secondary/30 rounded-lg">
              <p className="text-2xl font-semibold text-foreground">{schema.tasks?.length || 0}</p>
              <p className="text-xs text-muted-foreground">{tWorkflows("detail.tabs.tasks")}</p>
            </div>
            <div className="text-center p-4 bg-secondary/30 rounded-lg">
              <p className="text-2xl font-semibold text-foreground">{schema.dependencies?.length || 0}</p>
              <p className="text-xs text-muted-foreground">{tWorkflows("detail.overview.dependencies")}</p>
            </div>
          </div>
        </>
      )}

      {/* No Schema Warning */}
      {!schema && (
        <div className="p-4 bg-secondary/20 rounded-lg border border-border/40">
          <p className="text-sm text-muted-foreground">
            {tWorkflows("detail.overview.noSchema")}
          </p>
        </div>
      )}

      {/* Timestamps */}
      <div className="pt-4 border-t border-border/40">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">{tWorkflows("detail.overview.created")} </span>
            <span className="text-foreground">
              {workflow.created_at
                ? new Date(workflow.created_at).toLocaleString()
                : "—"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">{tWorkflows("detail.overview.updated")} </span>
            <span className="text-foreground">
              {workflow.updated_at
                ? new Date(workflow.updated_at).toLocaleString()
                : "—"}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
