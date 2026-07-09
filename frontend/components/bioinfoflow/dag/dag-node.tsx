/**
 * DAG Node Component
 *
 * Renders individual nodes in the DAG with classic lifecycle semantics:
 * - pending: Waiting (dashed border, muted)
 * - queued: Queued but unfinished (dashed border, warmer tint)
 * - running: Currently executing (solid border + pulse + spin icon)
 * - success: Completed (green border, entrance ring wave)
 * - failed: Execution failed (red border)
 */

import type React from "react"
import type { NodeProps } from "reactflow"
import { Handle, Position } from "reactflow"
import { cn } from "@/lib/utils"
import { CheckCircle2, Loader2, Clock, Circle, XCircle } from "@/lib/icons"

export type NodeStatus = "pending" | "queued" | "running" | "success" | "failed"

export type DagOrientation = "horizontal" | "vertical"

export interface PipelineNodeData {
  label: string
  status: NodeStatus
  source?: "schema" | "runtime"
  orientation?: DagOrientation
}

/**
 * Node status configuration
 * Defines icon, border color, and animation for each status
 */
const statusConfig: Record<NodeStatus, { icon: React.ReactNode; borderColor: string; animation?: string }> = {
  pending: {
    icon: <Circle className="h-3.5 w-3.5 text-muted-foreground" />,
    borderColor: "border-border border-dashed",
  },
  queued: {
    icon: <Clock className="h-3.5 w-3.5 text-warning" />,
    borderColor: "border-warning border-dashed",
  },
  running: {
    icon: <Loader2 className="h-3.5 w-3.5 text-foreground animate-spin motion-reduce:animate-none" />,
    borderColor: "border-foreground",
    animation: "animate-subtle-pulse motion-reduce:animate-none",
  },
  success: {
    icon: <CheckCircle2 className="h-3.5 w-3.5 text-success" />,
    borderColor: "border-success",
    animation: "animate-node-complete motion-reduce:animate-none",
  },
  failed: {
    icon: <XCircle className="h-3.5 w-3.5 text-destructive" />,
    borderColor: "border-destructive",
  },
}

/**
 * PipelineNode Component
 *
 * Custom node type for React Flow with lifecycle animations
 */
export function PipelineNode({ data }: NodeProps<PipelineNodeData>) {
  const config = statusConfig[data.status]
  const isSchema = data.source === "schema"
  const isHorizontal = data.orientation === "horizontal"
  const targetPos = isHorizontal ? Position.Left : Position.Top
  const sourcePos = isHorizontal ? Position.Right : Position.Bottom

  return (
    <div className="relative">
      {/* Ring wave on completion */}
      {data.status === "success" && (
        <div className="absolute inset-0 rounded-lg border-2 border-success animate-ring-wave motion-reduce:hidden" />
      )}

      <div
        className={cn(
          "relative rounded-lg border-2 bg-card px-4 py-2.5 min-w-[120px] shadow-sm transition-all duration-300",
          config.borderColor,
          config.animation,
          isSchema && "border-dashed",
          data.status === "queued" && "bg-warning/5",
          data.status === "success" && "shadow-[0_0_12px_var(--success-border)]",
          data.status === "failed" && "shadow-[0_0_12px_var(--error-border)]",
        )}
        data-status={data.status}
        data-source={data.source}
      >
        <Handle type="target" position={targetPos} className="!bg-border !w-2 !h-2 !border-0" />
        <div className="flex items-center gap-2">
          {config.icon}
          <span className="text-sm font-medium text-foreground">{data.label}</span>
          {isSchema && (
            <span className="text-2xs font-medium uppercase tracking-wider text-muted-foreground bg-secondary rounded px-1 py-0.5 leading-none">
              schema
            </span>
          )}
        </div>
        <Handle type="source" position={sourcePos} className="!bg-border !w-2 !h-2 !border-0" />
      </div>
    </div>
  )
}

/**
 * Export nodeTypes object for React Flow
 */
export const nodeTypes = {
  pipeline: PipelineNode,
}
