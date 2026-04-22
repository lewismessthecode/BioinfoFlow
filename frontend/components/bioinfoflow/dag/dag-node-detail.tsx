"use client"

import { useEffect, useRef, useCallback } from "react"
import { X, Clock, Container, Terminal } from "lucide-react"
import { cn } from "@/lib/utils"
import type { NodeStatus } from "./dag-node"

export interface NodeDetailData {
  id: string
  label: string
  displayLabel?: string
  status: NodeStatus
  duration?: number
  startedAt?: string
  inputs?: Record<string, string>
  outputs?: Record<string, string>
  logPreview?: string
  container?: string
}

interface DagNodeDetailProps {
  node: NodeDetailData
  onClose: () => void
}

const statusLabel: Record<NodeStatus, { text: string; className: string }> = {
  pending: { text: "PENDING", className: "text-muted-foreground" },
  queued: { text: "QUEUED", className: "text-muted-foreground" },
  running: { text: "RUNNING", className: "text-warning" },
  success: { text: "DONE", className: "text-success" },
  failed: { text: "FAILED", className: "text-destructive" },
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

function ParamSection({ title, params }: { title: string; params: Record<string, string> }) {
  const entries = Object.entries(params)
  if (entries.length === 0) return null

  return (
    <div>
      <div className="font-mono text-2xs uppercase tracking-widest text-muted-foreground mb-1.5">{title}</div>
      <div className="space-y-1">
        {entries.map(([key, value]) => (
          <div key={key} className="flex justify-between gap-2 font-mono text-xs-tight">
            <span className="text-muted-foreground truncate">{key}</span>
            <span className="text-foreground/80 truncate text-right">{value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function DagNodeDetail({ node, onClose }: DagNodeDetailProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const status = statusLabel[node.status]

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    },
    [onClose]
  )

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [handleKeyDown])

  return (
    <div
      ref={panelRef}
      className={cn(
        "absolute right-3 top-3 z-20 w-[280px]",
        "rounded-none border border-border bg-card/95 backdrop-blur-sm",
        "font-mono shadow-md",
        "animate-in slide-in-from-right-2 fade-in duration-200",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wide text-foreground truncate pr-2">
          {node.displayLabel ?? node.label}
        </span>
        <button
          onClick={onClose}
          className="text-muted-foreground hover:text-foreground transition-colors shrink-0"
          aria-label="Close detail panel"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Body */}
      <div className="px-3 py-2.5 space-y-3 text-xs">
        {/* Status + Duration row */}
        <div className="flex items-center justify-between">
          <span className={cn("font-mono text-xs-tight uppercase tracking-wider font-semibold", status.className)}>
            {status.text}
          </span>
          {node.duration != null && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span className="font-mono text-xs-tight">{formatDuration(node.duration)}</span>
            </span>
          )}
        </div>

        {/* Container */}
        {node.container && (
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Container className="h-3 w-3 shrink-0" />
            <span className="font-mono text-xs-tight truncate">{node.container}</span>
          </div>
        )}

        {/* Inputs */}
        {node.inputs && Object.keys(node.inputs).length > 0 && (
          <ParamSection title="Inputs" params={node.inputs} />
        )}

        {/* Outputs */}
        {node.outputs && Object.keys(node.outputs).length > 0 && (
          <ParamSection title="Outputs" params={node.outputs} />
        )}

        {/* Log preview */}
        {node.logPreview && (
          <div>
            <div className="flex items-center gap-1 mb-1.5">
              <Terminal className="h-3 w-3 text-muted-foreground" />
              <span className="font-mono text-2xs uppercase tracking-widest text-muted-foreground">Log</span>
            </div>
            <pre className="rounded-none border border-border bg-background/50 p-2 text-2xs leading-relaxed text-muted-foreground overflow-x-auto max-h-[120px] overflow-y-auto whitespace-pre-wrap">
              {node.logPreview}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
