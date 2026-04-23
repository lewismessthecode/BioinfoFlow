import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const copy: Record<string, string> = {
      pending: "Pending",
      queued: "Queued",
      preparing: "Preparing",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
      cancelled: "Cancelled",
    }

    if (key === "currentTask") {
      return `Current task: ${values?.task ?? ""}`
    }

    return copy[key] ?? key
  },
}))

import { RunStagePanel } from "@/components/bioinfoflow/run-stage-panel"

describe("RunStagePanel", () => {
  it("shows completed earlier stages and the current task for active runs", () => {
    render(<RunStagePanel status="running" currentTask="FASTQC sample-1" />)

    expect(screen.getByLabelText("pending done")).toBeInTheDocument()
    expect(screen.getByLabelText("queued done")).toBeInTheDocument()
    expect(screen.getByLabelText("preparing done")).toBeInTheDocument()
    expect(screen.getByLabelText("running active")).toBeInTheDocument()
    expect(screen.getByText("Current task: FASTQC sample-1")).toBeInTheDocument()
  })

  it("shows a terminal success badge and hides the in-flight task copy", () => {
    render(<RunStagePanel status="completed" currentTask="Should be hidden" />)

    expect(screen.getByText("Completed")).toBeInTheDocument()
    expect(screen.queryByText("Current task: Should be hidden")).not.toBeInTheDocument()
  })

  it("renders the cancelled terminal label", () => {
    render(<RunStagePanel status="cancelled" />)

    expect(screen.getByText("Cancelled")).toBeInTheDocument()
  })
})
