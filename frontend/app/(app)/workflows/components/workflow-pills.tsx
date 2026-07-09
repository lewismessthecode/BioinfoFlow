"use client"

import { GitBranch } from "@/lib/icons"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { Workflow } from "@/lib/types"

const ENGINE_STYLES = {
  wdl: {
    label: "WDL",
  },
  nextflow: {
    label: "Nextflow",
  },
} as const

export function engineStyleFor(engine: string) {
  return engine === "wdl" ? ENGINE_STYLES.wdl : ENGINE_STYLES.nextflow
}

interface WorkflowPillsProps {
  workflow: Workflow
  scaleLabel?: string | null
  showSource?: boolean
  hideVersion?: boolean
}

export function WorkflowPills({ workflow, scaleLabel, showSource, hideVersion }: WorkflowPillsProps) {
  const engine = engineStyleFor(workflow.engine)

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {scaleLabel && (
        <Badge
          variant="outline"
          className="metadata-pill metadata-pill--scale text-xs-tight capitalize"
        >
          {scaleLabel}
        </Badge>
      )}
      {showSource && (
        <Badge variant="outline" className="metadata-pill metadata-pill--source text-xs-tight uppercase tracking-[0.16em]">
          {workflow.source}
        </Badge>
      )}
      <Badge variant="outline" className={cn("metadata-pill metadata-pill--engine text-xs-tight", workflow.engine === "wdl" && "font-semibold")}>
        {engine.label}
      </Badge>
      {!hideVersion && (
        <Badge variant="outline" className="metadata-pill metadata-pill--version text-xs-tight font-mono gap-1">
          <GitBranch className="h-2.5 w-2.5" />
          {workflow.version}
        </Badge>
      )}
    </div>
  )
}
