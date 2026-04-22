import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { PipelineNode, type PipelineNodeData } from "@/components/bioinfoflow/dag/dag-node"

vi.mock("reactflow", () => ({
  Handle: (props: { type: string; position: string }) => (
    <div data-testid={`handle-${props.type}-${props.position}`} />
  ),
  Position: {
    Top: "top",
    Bottom: "bottom",
  },
}))

function renderNode(status: PipelineNodeData["status"]) {
  render(
    <PipelineNode
      id={`node-${status}`}
      type="pipeline"
      selected={false}
      isConnectable={false}
      xPos={0}
      yPos={0}
      zIndex={0}
      dragging={false}
      data={{ label: `Node ${status}`, status }}
    />
  )
}

describe("PipelineNode", () => {
  it("renders pending and queued nodes as unfinished dashed cards", () => {
    const { rerender } = render(
      <PipelineNode
        id="node-pending"
        type="pipeline"
        selected={false}
        isConnectable={false}
        xPos={0}
        yPos={0}
        zIndex={0}
        dragging={false}
        data={{ label: "Node pending", status: "pending" }}
      />
    )

    expect(screen.getByText("Node pending").closest("div.rounded-lg")).toHaveClass(
      "border-dashed"
    )

    rerender(
      <PipelineNode
        id="node-queued"
        type="pipeline"
        selected={false}
        isConnectable={false}
        xPos={0}
        yPos={0}
        zIndex={0}
        dragging={false}
        data={{ label: "Node queued", status: "queued" }}
      />
    )

    expect(screen.getByText("Node queued").closest("div.rounded-lg")).toHaveClass(
      "border-dashed"
    )
  })

  it("renders running and terminal nodes with the expected classic classes", () => {
    renderNode("running")
    expect(screen.getByText("Node running").closest("div.rounded-lg")).toHaveClass(
      "animate-subtle-pulse"
    )

    renderNode("success")
    expect(screen.getByText("Node success").closest("div.rounded-lg")).toHaveClass(
      "border-success"
    )

    renderNode("failed")
    expect(screen.getByText("Node failed").closest("div.rounded-lg")).toHaveClass(
      "border-destructive"
    )
  })
})
