import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { DagPanel } from "@/components/bioinfoflow/dag/dag-panel"
import { apiRequest } from "@/lib/api"
import type { DagData } from "@/lib/types"
import { renderAppPage } from "@/tests/app-test-utils"

const fitViewMock = vi.fn()
const savePositionMock = vi.fn()
const clearPositionsMock = vi.fn()
const apiRequestMock = vi.hoisted(() => vi.fn())
const persistedPositionsRef = vi.hoisted(() => ({
  current: {} as Record<string, { x: number; y: number }>,
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

vi.mock("@/hooks/use-dag-positions", () => ({
  usePersistedPositions: () => ({
    positions: persistedPositionsRef.current,
    savePosition: savePositionMock,
    clearPositions: clearPositionsMock,
  }),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: apiRequestMock,
  }
})

vi.mock("reactflow", async () => {
  const ReactModule = await vi.importActual<typeof import("react")>("react")

  function useNodesState<T>(initial: T[]) {
    const [nodes, setNodes] = ReactModule.useState(initial)
    return [nodes, setNodes, vi.fn()] as const
  }

  function useEdgesState<T>(initial: T[]) {
    const [edges, setEdges] = ReactModule.useState(initial)
    return [edges, setEdges, vi.fn()] as const
  }

  function MockReactFlow({
    nodes,
    edges,
    children,
    onInit,
  }: {
    nodes: Array<{ id: string; position: { x: number; y: number }; data: { status: string } }>
    edges: Array<{ id: string; source: string; target: string; data?: { sourceStatus?: string } }>
    children?: React.ReactNode
    onInit?: (instance: { fitView: typeof fitViewMock }) => void
  }) {
    ReactModule.useEffect(() => {
      onInit?.({ fitView: fitViewMock })
    }, [onInit])

    return (
      <div data-testid="reactflow">
        <div data-testid="nodes-json">{JSON.stringify(nodes)}</div>
        <div data-testid="edges-json">{JSON.stringify(edges)}</div>
        {children}
      </div>
    )
  }

  return {
    __esModule: true,
    default: MockReactFlow,
    Background: () => <div data-testid="rf-background" />,
    Controls: () => <div data-testid="rf-controls" />,
    MiniMap: () => <div data-testid="rf-minimap" />,
    Handle: () => <div data-testid="rf-handle" />,
    Position: {
      Top: "top",
      Bottom: "bottom",
      Left: "left",
      Right: "right",
    },
    MarkerType: {
      ArrowClosed: "arrowclosed",
    },
    useNodesState,
    useEdgesState,
  }
})

class ResizeObserverMock {
  observe() {}
  disconnect() {}
  unobserve() {}
}

const dagWithNode: DagData = {
  nodes: [
    {
      id: "fastqc",
      type: "pipeline",
      position: { x: 20, y: 40 },
      data: {
        label: "FASTQC",
        displayLabel: "FASTQC",
        status: "pending",
        inputs: { reads: "reads" },
        outputs: { report: "report" },
        container: "biocontainers/fastqc:0.12.1",
      },
    },
  ],
  edges: [],
}

describe("DagPanel", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock)
    vi.stubGlobal("fetch", vi.fn())
    apiRequestMock.mockReset()
    fitViewMock.mockReset()
    savePositionMock.mockReset()
    clearPositionsMock.mockReset()
    persistedPositionsRef.current = {}
    if (typeof window !== "undefined") {
      window.localStorage.clear()
    }
  })

  it("clears stale graph state when the incoming dag becomes empty", async () => {
    const { rerender } = renderAppPage(<DagPanel dag={dagWithNode} showHeader={false} />)

    expect(screen.getByTestId("nodes-json")).toHaveTextContent("\"fastqc\"")

    rerender(<DagPanel dag={{ nodes: [], edges: [] }} showHeader={false} />)

    await waitFor(() => {
      expect(screen.getByTestId("nodes-json")).toHaveTextContent("[]")
    })
    expect(screen.getByText("emptyState.title")).toBeInTheDocument()
  })

  it("resets persisted layout back to canonical dag positions", async () => {
    persistedPositionsRef.current = {
      fastqc: { x: 400, y: 500 },
    }

    renderAppPage(<DagPanel dag={dagWithNode} showHeader={false} />)

    expect(screen.getByTestId("nodes-json")).toHaveTextContent("\"x\":400")

    fireEvent.click(screen.getByRole("button", { name: "Reset layout" }))

    await waitFor(() => {
      expect(clearPositionsMock).toHaveBeenCalledTimes(1)
      // Default orientation is horizontal, so the canonical {x:20, y:40} is
      // swapped and rescaled (depth × 2.0, sibling × 0.45) to avoid wide-node
      // overlap when switching axes — landing at {x:80, y:9}.
      expect(screen.getByTestId("nodes-json")).toHaveTextContent("\"x\":80")
    })
  })

  it("loads missing run DAGs through the credential-aware API client", async () => {
    vi.mocked(apiRequest).mockResolvedValue({
      data: dagWithNode,
      meta: undefined,
    })

    renderAppPage(<DagPanel runId="run-authenticated" showHeader={false} />)

    await waitFor(() => {
      expect(screen.getByTestId("nodes-json")).toHaveTextContent("\"fastqc\"")
    })
    expect(apiRequest).toHaveBeenCalledWith("/runs/run-authenticated/dag")
    expect(fetch).not.toHaveBeenCalled()
  })
})
