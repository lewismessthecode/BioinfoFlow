import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  AgentActivityGroup,
  AgentToolCard,
} from "@/components/bioinfoflow/agent/agent-activity"
import type { ToolProgressView } from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "details.show": "Show details",
        "details.hide": "Hide details",
        "details.arguments": "Arguments",
        "details.input": "Input",
        "details.output": "Output",
        "details.error": "Error",
        "status.pending": "Pending",
        "status.running": "Running",
        "status.completed": "Completed",
        "status.failed": "Failed",
        "status.blocked": "Blocked",
        "status.cancelled": "Cancelled",
        "status.interaction_required": "Needs approval",
        "group.parallel": `${values?.count ?? 0} tools running in parallel`,
        "group.serial": `${values?.count ?? 0} tools running in sequence`,
        "group.mixed": `${values?.count ?? 0} tool activities`,
        "group.generic": `${values?.count ?? 0} tool activities`,
      }
      return copy[key] ?? key
    },
}))

const runningTool: ToolProgressView = {
  call_id: "call-read-1",
  group_id: "group-1",
  execution_mode: "parallel",
  name: "read",
  display_name: "read",
  category: "read",
  summary: "Read workflow.nf",
  arguments: { path: "workflow.nf" },
  status: "running",
  revision: 2,
  started_at: "2026-08-15T08:00:00Z",
  completed_at: null,
  input_summary: "workflow.nf",
  output_summary: null,
  error: null,
}

describe("AgentToolCard", () => {
  it("shows the public tool summary and reveals structured details on demand", async () => {
    const user = userEvent.setup()
    renderWithProviders(<AgentToolCard tool={runningTool} />)

    expect(screen.getByText("read")).toBeInTheDocument()
    expect(screen.getByText("Read workflow.nf")).toBeInTheDocument()
    expect(screen.getByText("Running")).toBeInTheDocument()
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Show details" }))

    expect(screen.getByText("Arguments").parentElement).toHaveTextContent(
      '"path": "workflow.nf"',
    )
  })

  it("normalizes rounded duration across minute boundaries", () => {
    renderWithProviders(
      <AgentToolCard
        tool={{
          ...runningTool,
          status: "completed",
          started_at: "2026-08-15T08:00:00.000Z",
          completed_at: "2026-08-15T08:01:59.600Z",
        }}
      />,
    )

    expect(screen.getByText("2m 0s")).toBeInTheDocument()
  })
})

describe("AgentActivityGroup", () => {
  it("expands an active parallel group by default without inferring execution mode", () => {
    renderWithProviders(
      <AgentActivityGroup
        tools={[
          runningTool,
          {
            ...runningTool,
            call_id: "call-read-2",
            name: "read",
            summary: "Read params.json",
            arguments: { path: "params.json" },
          },
        ]}
        executionMode="parallel"
      />,
    )

    expect(screen.getByRole("button", { name: /2 tools running in parallel/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    )
    expect(screen.getByText("Read workflow.nf")).toBeInTheDocument()
    expect(screen.getByText("Read params.json")).toBeInTheDocument()
  })
})
