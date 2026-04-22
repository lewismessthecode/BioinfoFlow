"use client"

import { type EdgeProps, getBezierPath, BaseEdge } from "reactflow"

/**
 * Animated DAG Edge
 *
 * Renders edges with traveling particle dots based on pipeline state:
 * - Pending/queued: dashed unfinished line
 * - Running: solid warning line with traveling particles
 * - Success/failed: solid terminal-state line
 */

export interface AnimatedEdgeData {
  sourceStatus?: "pending" | "queued" | "running" | "success" | "failed"
}

export function AnimatedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  markerEnd,
  data,
}: EdgeProps<AnimatedEdgeData>) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  const sourceStatus = data?.sourceStatus ?? "pending"
  const isActive = sourceStatus === "running" || sourceStatus === "queued"
  const isComplete = sourceStatus === "success"
  const isFailed = sourceStatus === "failed"

  let edgeColor = (style?.stroke as string) ?? "var(--border)"

  if (isComplete) {
    edgeColor = "var(--success)"
  } else if (isFailed) {
    edgeColor = "var(--destructive)"
  } else if (isActive) {
    edgeColor = "var(--warning)"
  }

  const edgeOpacity = sourceStatus === "pending" ? 0.3 : sourceStatus === "queued" ? 0.55 : 0.8
  const resolvedMarkerEnd =
    markerEnd && typeof markerEnd === "object" ? { ...markerEnd, color: edgeColor } : markerEnd

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={resolvedMarkerEnd}
        style={{
          ...style,
          stroke: edgeColor,
          strokeWidth: isActive ? 2.5 : 2,
          strokeDasharray:
            sourceStatus === "pending" || sourceStatus === "queued" ? "6 6" : undefined,
          strokeOpacity: edgeOpacity,
          transition: "stroke 0.4s ease, stroke-width 0.3s ease, stroke-opacity 0.3s ease",
        }}
      />

      {/* Traveling particles for active edges */}
      {isActive && (
        <>
          <circle r="2.5" fill="var(--warning)" opacity="0.9">
            <animateMotion dur="1.5s" repeatCount="indefinite" path={edgePath} />
          </circle>
          <circle r="2" fill="var(--warning)" opacity="0.5">
            <animateMotion dur="1.5s" repeatCount="indefinite" path={edgePath} begin="0.5s" />
          </circle>
          <circle r="1.5" fill="var(--warning)" opacity="0.3">
            <animateMotion dur="1.5s" repeatCount="indefinite" path={edgePath} begin="1s" />
          </circle>
        </>
      )}
    </>
  )
}

export const edgeTypes = {
  animated: AnimatedEdge,
}
