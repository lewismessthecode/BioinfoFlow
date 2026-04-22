import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AnimatedEdge } from "@/components/bioinfoflow/dag/dag-edge"

vi.mock("reactflow", () => ({
  BaseEdge: ({
    id,
    path,
    style,
    markerEnd,
  }: {
    id: string
    path: string
    style?: Record<string, unknown>
    markerEnd?: Record<string, unknown>
  }) => (
    <div
      data-testid={`edge-${id}`}
      data-path={path}
      data-stroke={String(style?.stroke)}
      data-stroke-dasharray={String(style?.strokeDasharray ?? "")}
      data-stroke-width={String(style?.strokeWidth ?? "")}
      data-stroke-opacity={String(style?.strokeOpacity ?? "")}
      data-marker-end-color={String(markerEnd?.color ?? "")}
    />
  ),
  getBezierPath: () => ["M0,0 C10,10 20,20 30,30"],
}))

function renderEdge(sourceStatus: "pending" | "queued" | "running" | "success" | "failed") {
  return render(
    <svg>
      <AnimatedEdge
        id={`edge-${sourceStatus}`}
        sourceX={0}
        sourceY={0}
        targetX={10}
        targetY={10}
        sourcePosition={"bottom" as never}
        targetPosition={"top" as never}
        markerEnd={{ type: "arrowclosed", color: "var(--foreground)" } as never}
        data={{ sourceStatus }}
      />
    </svg>
  )
}

describe("AnimatedEdge", () => {
  it("renders pending and queued edges with unfinished styling", () => {
    renderEdge("pending")
    expect(screen.getByTestId("edge-edge-pending")).toHaveAttribute(
      "data-stroke-dasharray",
      "6 6"
    )

    renderEdge("queued")
    expect(screen.getByTestId("edge-edge-queued")).toHaveAttribute(
      "data-stroke",
      "var(--warning)"
    )
  })

  it("renders running, success, and failed edges with classic status colors", () => {
    const running = renderEdge("running")
    expect(running.container.querySelectorAll("circle").length).toBeGreaterThan(0)

    renderEdge("success")
    expect(screen.getByTestId("edge-edge-success")).toHaveAttribute(
      "data-stroke",
      "var(--success)"
    )
    expect(screen.getByTestId("edge-edge-success")).toHaveAttribute(
      "data-marker-end-color",
      "var(--success)"
    )

    renderEdge("failed")
    expect(screen.getByTestId("edge-edge-failed")).toHaveAttribute(
      "data-stroke",
      "var(--destructive)"
    )
    expect(screen.getByTestId("edge-edge-failed")).toHaveAttribute(
      "data-marker-end-color",
      "var(--destructive)"
    )
  })
})
