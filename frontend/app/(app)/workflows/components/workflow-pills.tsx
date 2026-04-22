"use client"

import { GitBranch } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { Workflow } from "@/lib/types"

const ENGINE_STYLES = {
  wdl: {
    label: "WDL",
    classes: "bg-blue-50/70 text-blue-700 border-blue-200/60 dark:bg-blue-950/30 dark:text-blue-300 dark:border-blue-800/40",
  },
  nextflow: {
    label: "Nextflow",
    classes: "bg-emerald-50/70 text-emerald-700 border-emerald-200/60 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-800/40",
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
          className="text-xs-tight capitalize bg-amber-50/70 text-amber-700 border-amber-200/60 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40"
        >
          {scaleLabel}
        </Badge>
      )}
      {showSource && (
        <Badge variant="secondary" className="text-xs-tight uppercase tracking-wide">
          {workflow.source}
        </Badge>
      )}
      <Badge variant="outline" className={`text-xs-tight ${engine.classes}`}>
        {engine.label}
      </Badge>
      {!hideVersion && (
        <Badge variant="outline" className="text-xs-tight font-mono gap-1">
          <GitBranch className="h-2.5 w-2.5" />
          {workflow.version}
        </Badge>
      )}
    </div>
  )
}
