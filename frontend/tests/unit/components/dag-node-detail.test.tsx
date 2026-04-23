import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { DagNodeDetail, type NodeDetailData } from "@/components/bioinfoflow/dag/dag-node-detail"

const node: NodeDetailData = {
  id: "fastqc",
  label: "FASTQC",
  displayLabel: "FASTQC sample_1",
  status: "running",
  duration: 65,
  inputs: {
    reads: "reads.fastq.gz",
  },
  outputs: {
    report: "fastqc.html",
  },
  logPreview: "task started\nquality checks complete",
  container: "biocontainers/fastqc:0.12.1",
}

describe("DagNodeDetail", () => {
  it("renders the key execution metadata for the selected node", () => {
    render(<DagNodeDetail node={node} onClose={vi.fn()} />)

    expect(screen.getByText("FASTQC sample_1")).toBeInTheDocument()
    expect(screen.getByText("RUNNING")).toBeInTheDocument()
    expect(screen.getByText("1m 5s")).toBeInTheDocument()
    expect(screen.getByText("biocontainers/fastqc:0.12.1")).toBeInTheDocument()
    expect(screen.getByText("Inputs")).toBeInTheDocument()
    expect(screen.getByText("Outputs")).toBeInTheDocument()
    expect(screen.getByText(/task started/)).toBeInTheDocument()
  })

  it("closes from both the explicit close affordance and the Escape shortcut", () => {
    const onClose = vi.fn()

    render(<DagNodeDetail node={node} onClose={onClose} />)

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole("button", { name: "Close detail panel" }))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
