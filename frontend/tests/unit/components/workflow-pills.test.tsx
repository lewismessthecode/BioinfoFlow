import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { WorkflowPills } from "@/app/(app)/workflows/components/workflow-pills"
import type { Workflow } from "@/lib/types"

const workflow: Workflow = {
  id: "wf-1",
  name: "flaky-retry-mini",
  source: "local",
  engine: "nextflow",
  version: "1.0.0",
}

describe("WorkflowPills", () => {
  it("uses appearance-aware metadata pill classes instead of hardcoded palettes", () => {
    render(<WorkflowPills workflow={workflow} scaleLabel="local" showSource hideVersion />)

    expect(screen.getAllByText("local")[0].className).toContain("metadata-pill metadata-pill--scale")
    expect(screen.getAllByText("local")[1].className).toContain("metadata-pill metadata-pill--source")
    expect(screen.getByText("Nextflow").className).toContain("metadata-pill metadata-pill--engine")
    expect(screen.getByText("Nextflow").className).not.toMatch(/bg-(emerald|blue|amber)/)
  })
})
