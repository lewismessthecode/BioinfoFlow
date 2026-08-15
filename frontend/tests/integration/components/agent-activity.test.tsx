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
        "category.read": "Reading",
        "category.command": "Commands",
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
  public_details: [
    {
      id: "command",
      kind: "command",
      label: null,
      value: "nextflow run workflow.nf",
      format: "code",
      copyable: true,
      truncated: false,
      redacted: false,
    },
  ],
}

describe("AgentToolCard", () => {
  it("keeps command details unmounted until the whole summary row is expanded", async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentToolCard tool={{ ...runningTool, status: "completed" }} />,
    )

    expect(screen.getByText("read")).toBeInTheDocument()
    expect(screen.getByText("Read workflow.nf")).toBeInTheDocument()
    expect(screen.queryByText("nextflow run workflow.nf")).not.toBeInTheDocument()

    const summaryRow = screen.getByRole("button", { name: /Show details/i })
    expect(summaryRow).toHaveTextContent("Read workflow.nf")
    await user.click(summaryRow)

    expect(screen.getByText("nextflow run workflow.nf")).toBeInTheDocument()
  })

  it("preserves the user's disclosure choice across live status revisions", async () => {
    const user = userEvent.setup()
    const view = renderWithProviders(
      <AgentToolCard tool={{ ...runningTool, status: "completed" }} />,
    )

    await user.click(screen.getByRole("button", { name: /Show details/i }))
    expect(screen.getByText("nextflow run workflow.nf")).toBeInTheDocument()

    view.rerender(<AgentToolCard tool={{ ...runningTool, status: "running" }} />)

    expect(screen.getByText("nextflow run workflow.nf")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Hide details/i })).toHaveAttribute(
      "aria-expanded",
      "true",
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

  it("keeps long Harness display names inside the card", () => {
    renderWithProviders(
      <AgentToolCard
        tool={{
          ...runningTool,
          display_name: "read_a_very_long_provider_specific_tool_display_name",
        }}
      />,
    )

    const label = screen.getByTitle(
      "read_a_very_long_provider_specific_tool_display_name",
    )
    expect(label).toHaveClass("truncate")
    expect(label).toHaveClass("min-w-0")
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

  it("localizes public tool categories instead of rendering protocol values", () => {
    renderWithProviders(
      <AgentActivityGroup
        tools={[
          runningTool,
          {
            ...runningTool,
            call_id: "call-command-1",
            name: "bash",
            display_name: "bash",
            category: "command",
            summary: "Run workflow",
          },
        ]}
      />,
    )

    expect(screen.getByText("Reading")).toBeInTheDocument()
    expect(screen.getByText("Commands")).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "read" })).not.toBeInTheDocument()
    expect(
      screen.queryByRole("heading", { name: "command" }),
    ).not.toBeInTheDocument()
  })

  it("preserves interleaved model-call order while grouping contiguous categories", () => {
    renderWithProviders(
      <AgentActivityGroup
        tools={[
          runningTool,
          {
            ...runningTool,
            call_id: "call-command-1",
            name: "bash",
            display_name: "bash",
            category: "command",
            summary: "Run workflow",
          },
          {
            ...runningTool,
            call_id: "call-read-2",
            summary: "Read results.json",
            arguments: { path: "results.json" },
          },
        ]}
      />,
    )

    expect(
      screen
        .getAllByTestId("agent-tool-card")
        .map((card) => card.textContent),
    ).toEqual([
      expect.stringContaining("Read workflow.nf"),
      expect.stringContaining("Run workflow"),
      expect.stringContaining("Read results.json"),
    ])
    expect(
      screen
        .getAllByRole("heading", { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(["Reading", "Commands", "Reading"])
  })

  it("renders grouped tools as flat rows instead of nested bordered cards", () => {
    renderWithProviders(
      <AgentActivityGroup
        tools={[
          runningTool,
          {
            ...runningTool,
            call_id: "call-read-2",
            summary: "Read params.json",
          },
        ]}
      />,
    )

    const group = screen.getByTestId("agent-activity-group")
    const childRows = group.querySelectorAll('[data-testid="agent-tool-card"]')
    expect(childRows).toHaveLength(2)
    for (const row of childRows) {
      expect(row).toHaveAttribute("data-grouped", "true")
      expect(row).not.toHaveClass("border")
    }
  })
})
