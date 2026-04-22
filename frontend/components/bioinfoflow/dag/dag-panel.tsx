/**
 * DAG Panel Component
 *
 * Classic-only DAG visualization for workflow previews and live runs.
 */

"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import ReactFlow, {
  type Edge,
  type Node,
  type NodeDragHandler,
  type ReactFlowInstance,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  Position,
  useEdgesState,
  useNodesState,
} from "reactflow"
import "reactflow/dist/style.css"
import { AlertCircle, MoveHorizontal, MoveVertical, Network, RotateCcw } from "lucide-react"

import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert"
import type { DagData, Run } from "@/lib/types"
import { cn } from "@/lib/utils"
import { usePersistedPositions } from "@/hooks/use-dag-positions"

import { DagBackground } from "./dag-background"
import { edgeTypes, type AnimatedEdgeData } from "./dag-edge"
import { nodeTypes, type DagOrientation, type NodeStatus, type PipelineNodeData } from "./dag-node"
import { DagNodeDetail, type NodeDetailData } from "./dag-node-detail"
import { DagHeader } from "./dag-header"
import { useDagRuns, useDagWorkflowGroups, useDagFetch } from "./dag-data-hooks"

const ORIENTATION_STORAGE_KEY = "bif:dag:orientation"
const DEFAULT_ORIENTATION: DagOrientation = "horizontal"

export interface DagPanelProps {
  workflowId?: string
  runId?: string | null
  dag?: DagData | null
  variant?: "panel" | "embedded"
  title?: string
  showHeader?: boolean
  showRunSelector?: boolean
  projectId?: string | null
  workflowName?: string
  onRunSelect?: (run: Run | null) => void
  onNodeSelect?: (nodeId: string | null) => void
}

export function DagPanel({
  workflowId,
  runId,
  dag,
  variant = "panel",
  title,
  showHeader: showHeaderProp,
  showRunSelector = false,
  projectId,
  workflowName,
  onRunSelect,
  onNodeSelect,
}: DagPanelProps) {
  const tDag = useTranslations("dag")

  const [nodes, setNodes, onNodesChange] = useNodesState<PipelineNodeData>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [orientation, setOrientationState] = useState<DagOrientation>(() => {
    if (typeof window === "undefined") return DEFAULT_ORIENTATION
    try {
      const stored = window.localStorage.getItem(ORIENTATION_STORAGE_KEY)
      if (stored === "horizontal" || stored === "vertical") return stored
    } catch {
      // ignore — sandboxed storage
    }
    return DEFAULT_ORIENTATION
  })
  const containerRef = useRef<HTMLDivElement>(null)
  const canonicalPositionsRef = useRef<Record<string, { x: number; y: number }>>({})

  const isHorizontal = orientation === "horizontal"

  const isEmbedded = variant === "embedded"
  const showHeader = showHeaderProp !== undefined ? showHeaderProp : !isEmbedded
  const showRunSelect = showHeader && showRunSelector && !!onRunSelect

  const { workflowGroups, selectedGroupIndex, setSelectedGroupIndex, workflowGroupsLoading, selectedGroup } =
    useDagWorkflowGroups(projectId)
  const { runs, runsLoading, runsError } = useDagRuns(projectId, showRunSelect)

  const activeWorkflowId = selectedGroup?.pinned_workflow.id ?? null
  const effectiveWorkflowId = workflowId ?? activeWorkflowId
  const dagId = runId ?? effectiveWorkflowId ?? "demo"
  const { positions: persistedPositions, savePosition, clearPositions } = usePersistedPositions(dagId)

  const setOrientation = useCallback(
    (next: DagOrientation) => {
      setOrientationState((prev) => {
        if (prev === next) return prev
        // Persisted positions are tied to the previous axis layout;
        // discard them so the canonical layout re-applies cleanly.
        clearPositions()
        return next
      })
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(ORIENTATION_STORAGE_KEY, next)
        } catch {
          // ignore
        }
      }
    },
    [clearPositions]
  )

  const selectedGroupName = selectedGroup?.name ?? null

  const displayName = useMemo(() => {
    if (title) return title
    if (workflowName) return workflowName
    if (selectedGroupName) return selectedGroupName
    if (runId) return `Run ${runId.slice(0, 8)}`
    if (workflowId) return `Workflow ${workflowId.slice(0, 8)}`
    return ""
  }, [title, workflowName, selectedGroupName, runId, workflowId])

  const edgeStyle = useMemo(
    () => ({
      stroke: "var(--foreground)",
      strokeWidth: 2,
      strokeOpacity: 0.4,
    }),
    []
  )

  const fitView = useCallback(() => {
    rfInstance?.fitView({ padding: 0.2, duration: 200 })
  }, [rfInstance])

  const clearGraph = useCallback(() => {
    canonicalPositionsRef.current = {}
    setNodes([])
    setEdges([])
    setSelectedNodeId(null)
    onNodeSelect?.(null)
  }, [onNodeSelect, setEdges, setNodes])

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<PipelineNodeData>) => {
      setSelectedNodeId((prev) => (prev === node.id ? null : node.id))
      onNodeSelect?.(node.id)
    },
    [onNodeSelect]
  )

  const handlePaneClick = useCallback(() => {
    setSelectedNodeId(null)
    onNodeSelect?.(null)
  }, [onNodeSelect])

  useEffect(() => {
    setNodes((currentNodes) =>
      currentNodes.map((node) => ({
        ...node,
        data: { ...node.data, selected: node.id === selectedNodeId },
      }))
    )
  }, [selectedNodeId, setNodes])

  const selectedNodeDetail: NodeDetailData | null = useMemo(() => {
    if (!selectedNodeId) return null
    const node = nodes.find((item) => item.id === selectedNodeId)
    if (!node) return null
    const data = node.data as PipelineNodeData & {
      displayLabel?: string
      duration?: number
      startedAt?: string
      inputs?: Record<string, string>
      outputs?: Record<string, string>
      logPreview?: string
      container?: string
    }
    return {
      id: node.id,
      label: data.label,
      displayLabel: data.displayLabel,
      status: data.status,
      duration: data.duration,
      startedAt: data.startedAt,
      inputs: data.inputs,
      outputs: data.outputs,
      logPreview: data.logPreview,
      container: data.container,
    }
  }, [nodes, selectedNodeId])

  const handleNodeDragStop: NodeDragHandler = useCallback(
    (_event, node) => {
      savePosition(node.id, node.position.x, node.position.y)
    },
    [savePosition]
  )

  const handleResetLayout = useCallback(() => {
    clearPositions()
    setNodes((currentNodes) =>
      currentNodes.map((node) => ({
        ...node,
        position: canonicalPositionsRef.current[node.id] ?? node.position,
      }))
    )
    setTimeout(fitView, 50)
  }, [clearPositions, fitView, setNodes])

  useEffect(() => {
    if (!rfInstance || !containerRef.current) return

    const observer = new ResizeObserver(() => {
      window.requestAnimationFrame(fitView)
    })

    observer.observe(containerRef.current)
    const timeoutId = window.setTimeout(fitView, 100)

    return () => {
      window.clearTimeout(timeoutId)
      observer.disconnect()
    }
  }, [fitView, rfInstance, nodes.length])

  const applyDagData = useCallback(
    (dagData: DagData) => {
      if (!dagData.nodes?.length) {
        clearGraph()
        return
      }

      // Backend lays out nodes top→bottom (depth → y, sibling → x) with
      // NODE_Y_SPACING=140 (depth) and NODE_X_SPACING=220 (sibling), calibrated
      // for short, wide nodes flowing vertically. Swapping axes for horizontal
      // mode without rescaling packs ~180px-wide nodes into a 140px slot,
      // which makes them overlap and hides the connecting edges. Rebalance:
      // stretch the new depth axis (was y) to give wide nodes breathing room,
      // compress the new sibling axis (was x) since stacked nodes are short.
      const HORIZONTAL_DEPTH_SCALE = 2.0
      const HORIZONTAL_SIBLING_SCALE = 0.45
      // Edgeless DAGs with multiple nodes (e.g. Nextflow preview with no
      // extracted dependencies) land every node at depth 0, so the backend
      // already emits a horizontal row (constant y, varying x). The axis swap
      // below would collapse that row into a vertical stack, so pass those
      // positions through unchanged. A single-node DAG still goes through the
      // swap so its position matches the canonical rescaled layout.
      const isEdgelessRow = !dagData.edges?.length && dagData.nodes.length > 1
      const orient = (raw: { x: number; y: number }) =>
        isHorizontal && !isEdgelessRow
          ? { x: raw.y * HORIZONTAL_DEPTH_SCALE, y: raw.x * HORIZONTAL_SIBLING_SCALE }
          : raw

      canonicalPositionsRef.current = Object.fromEntries(
        dagData.nodes.map((node) => [node.id, orient(node.position)])
      )

      const newNodes: Node<PipelineNodeData>[] = dagData.nodes.map((node) => ({
        id: node.id,
        type: "pipeline",
        position: persistedPositions[node.id] ?? orient(node.position),
        sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
        targetPosition: isHorizontal ? Position.Left : Position.Top,
        data: {
          label: node.data.label,
          status: node.data.status,
          orientation,
          ...(node.data.displayLabel && { displayLabel: node.data.displayLabel }),
          ...(node.data.duration != null && { duration: node.data.duration }),
          ...(node.data.startedAt && { startedAt: node.data.startedAt }),
          ...(node.data.inputs && { inputs: node.data.inputs }),
          ...(node.data.outputs && { outputs: node.data.outputs }),
          ...(node.data.logPreview && { logPreview: node.data.logPreview }),
          ...(node.data.container && { container: node.data.container }),
        },
      }))

      const nodeStatusMap = new Map<string, NodeStatus>()
      for (const node of newNodes) {
        nodeStatusMap.set(node.id, node.data.status)
      }

      const nodeIds = new Set(newNodes.map((node) => node.id))
      const newEdges: Edge[] = dagData.edges
        .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
        .map((edge) => ({
          id: edge.id,
          source: edge.source,
          target: edge.target,
          animated: edge.animated,
          type: "animated",
          data: { sourceStatus: nodeStatusMap.get(edge.source) ?? "pending" } satisfies AnimatedEdgeData,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: "var(--foreground)",
            width: 14,
            height: 14,
          },
          style: edgeStyle,
        }))

      setNodes(newNodes)
      setEdges(newEdges)

      if (rfInstance) {
        setTimeout(() => {
          rfInstance.fitView({ padding: 0.2, duration: 200 })
        }, 50)
      }
    },
    [clearGraph, edgeStyle, isHorizontal, orientation, persistedPositions, rfInstance, setEdges, setNodes]
  )

  const { isLoading, error } = useDagFetch(runId, effectiveWorkflowId, dag, applyDagData, clearGraph)

  const showMiniMap = nodes.length >= 8

  return (
    <div className="h-full w-full relative overflow-hidden">
      <DagBackground />

      {showHeader && (
        <DagHeader
          displayName={displayName}
          workflowGroups={workflowGroups}
          selectedGroupIndex={selectedGroupIndex}
          onGroupChange={setSelectedGroupIndex}
          workflowGroupsLoading={workflowGroupsLoading}
          isLoading={isLoading}
          showRunSelect={showRunSelect}
          runId={runId}
          runs={runs}
          runsLoading={runsLoading}
          runsError={runsError}
          onRunSelect={onRunSelect}
        />
      )}

      <div ref={containerRef} className={cn("relative", showHeader ? "h-[calc(100%-49px)]" : "h-full")}>
        {error && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
            <Alert variant="destructive" className="max-w-sm">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>{tDag("error.title")}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          </div>
        )}

        {!isLoading && !error && nodes.length === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80" role="status">
            <div className="text-center text-muted-foreground">
              <Network className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">{tDag("emptyState.title")}</p>
              <p className="text-xs mt-1">{tDag("emptyState.description")}</p>
            </div>
          </div>
        )}

        {selectedNodeDetail && (
          <DagNodeDetail
            node={selectedNodeDetail}
            onClose={() => {
              setSelectedNodeId(null)
              onNodeSelect?.(null)
            }}
          />
        )}

        <div className="absolute left-3 bottom-[120px] z-10 flex flex-col gap-1">
          <button
            onClick={handleResetLayout}
            className="flex items-center justify-center h-7 w-7 border border-border bg-background/90 text-foreground/70 hover:text-foreground hover:bg-accent/30 transition-colors rounded-md"
            aria-label="Reset layout"
            title="Reset layout"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setOrientation(isHorizontal ? "vertical" : "horizontal")}
            className="flex items-center justify-center h-7 w-7 border border-border bg-background/90 text-foreground/70 hover:text-foreground hover:bg-accent/30 transition-colors rounded-md"
            aria-label={isHorizontal ? "Switch to vertical layout" : "Switch to horizontal layout"}
            title={isHorizontal ? "Switch to vertical layout" : "Switch to horizontal layout"}
          >
            {isHorizontal ? (
              <MoveVertical className="h-3.5 w-3.5" />
            ) : (
              <MoveHorizontal className="h-3.5 w-3.5" />
            )}
          </button>
        </div>

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onInit={setRfInstance}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
          onNodeDragStop={handleNodeDragStop}
          fitView
          minZoom={0.1}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
          defaultEdgeOptions={{
            style: edgeStyle,
            type: "smoothstep",
            markerEnd: { type: MarkerType.ArrowClosed, color: "var(--foreground)", width: 14, height: 14 },
          }}
        >
          <Background
            color="var(--dag-dot-bg)"
            gap={20}
            size={1}
          />
          <Controls
            className={cn(
              "!bg-background !border-border overflow-hidden shadow-sm !rounded-lg",
              "[&>button]:!bg-background [&>button]:!border-border [&>button]:!text-foreground",
              "[&>button:hover]:!bg-accent [&>button:hover]:!text-accent-foreground [&>button>svg]:!fill-current",
              "bg-background/80 border-border"
            )}
            showInteractive={false}
          />
          {showMiniMap && (
            <MiniMap
              className="!bg-background/90 !border-border !rounded-lg"
              nodeColor={(node) => {
                const status = (node.data as PipelineNodeData)?.status
                if (status === "success") return "var(--success)"
                if (status === "running") return "var(--warning)"
                if (status === "failed") return "var(--destructive)"
                if (status === "queued") return "var(--warning)"
                return "var(--muted-foreground)"
              }}
              maskColor="var(--dag-minimap-mask)"
              pannable
              zoomable
            />
          )}
        </ReactFlow>
      </div>
    </div>
  )
}
