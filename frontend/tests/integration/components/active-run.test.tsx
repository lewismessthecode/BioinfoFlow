import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ActiveRun } from "@/components/bioinfoflow/agent/active-run"
import type { ActiveRunView, ToolProgressView } from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentRun.title": "Agent run in progress",
        "agentRun.status.running": "Running",
        "agentRun.status.waiting_user": "Waiting for input",
        "agentRun.phase.model": "Working with the model",
        "agentRun.phase.tools": "Using tools",
        "agentRun.phase.interaction": "Waiting for input",
        "agentRun.progress.actions": `${values?.completed ?? 0} of ${values?.total ?? 0} actions finished`,
        "agentRun.progress.label": "Tool progress",
        "agentRun.reasoning": "Thinking summary",
        "agentRun.response": "Response",
        "agentActivity.details.show": "Show details",
        "agentActivity.details.hide": "Hide details",
        "agentActivity.details.arguments": "Arguments",
        "agentActivity.details.input": "Input",
        "agentActivity.details.output": "Output",
        "agentActivity.details.error": "Error",
        "agentActivity.status.pending": "Pending",
        "agentActivity.status.running": "Running",
        "agentActivity.status.completed": "Completed",
        "agentActivity.status.failed": "Failed",
        "agentActivity.status.blocked": "Blocked",
        "agentActivity.status.cancelled": "Cancelled",
        "agentActivity.status.interaction_required": "Needs approval",
        "agentActivity.group.parallel": `${values?.count ?? 0} tools running in parallel`,
        "agentActivity.group.serial": `${values?.count ?? 0} tools running in sequence`,
        "agentActivity.group.mixed": `${values?.count ?? 0} tool activities`,
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const baseTool: ToolProgressView = {
  call_id: "call-1",
  group_id: "parallel-read",
  execution_mode: "parallel",
  name: "read",
  display_name: "Read",
  category: "read",
  summary: "Read workflow.nf",
  arguments: { path: "workflow.nf" },
  status: "completed",
  revision: 2,
  started_at: "2026-08-15T08:00:00Z",
  completed_at: "2026-08-15T08:00:01Z",
  input_summary: null,
  output_summary: "Read 42 lines",
  error: null,
}

function activeRun(): ActiveRunView {
  return {
    run: {
      id: "run-1",
      session_id: "session-1",
      status: "running",
      phase: "tools",
      revision: 4,
      started_at: "2026-08-15T08:00:00Z",
      completed_at: null,
      termination_reason: null,
      error: null,
      created_at: "2026-08-15T08:00:00Z",
      updated_at: "2026-08-15T08:00:03Z",
    },
    assistant_draft: {
      id: "draft-1",
      run_id: "run-1",
      parts: [
        {
          id: "reasoning-1",
          type: "reasoning_summary",
          text: "I should inspect the workflow and parameters together.",
          end_offset: 53,
        },
        {
          id: "text-1",
          type: "text",
          text: "I found the workflow. Next I am checking its inputs.",
          end_offset: 52,
        },
      ],
    },
    tool_progress: [
      baseTool,
      {
        ...baseTool,
        call_id: "call-2",
        summary: "Read params.json",
        arguments: { path: "params.json" },
        status: "running",
        completed_at: null,
        output_summary: null,
      },
      {
        ...baseTool,
        call_id: "call-3",
        group_id: "validate-inputs",
        execution_mode: "serial",
        name: "bash",
        display_name: "Shell",
        category: "command",
        summary: "Validate workflow inputs",
        arguments: { command: "nextflow config" },
        status: "pending",
        started_at: null,
        completed_at: null,
        output_summary: null,
      },
    ],
    pending_interaction: null,
  }
}

describe("ActiveRun", () => {
  it("renders streamed response and thinking parts in their original order", () => {
    const run = activeRun()
    run.tool_progress = []
    run.assistant_draft = {
      id: "draft-ordered",
      run_id: "run-1",
      parts: [
        {
          id: "text-first",
          type: "text",
          text: "First response segment",
          end_offset: 22,
        },
        {
          id: "thinking-middle",
          type: "reasoning_summary",
          text: "Middle thinking segment",
          end_offset: 23,
        },
        {
          id: "text-last",
          type: "text",
          text: "Last response segment",
          end_offset: 21,
        },
      ],
    }

    renderWithProviders(<ActiveRun activeRun={run} />)

    const first = screen.getByText("First response segment")
    const middle = screen.getByText("Middle thinking segment")
    const last = screen.getByText("Last response segment")

    expect(first.compareDocumentPosition(middle)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
    expect(middle.compareDocumentPosition(last)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })

  it("separates streamed thinking and response while showing authoritative phase and tool progress", () => {
    renderWithProviders(<ActiveRun activeRun={activeRun()} />)

    expect(
      screen.getByRole("region", { name: "Agent run in progress" }),
    ).toBeInTheDocument()
    expect(screen.getByTestId("agent-active-run")).toHaveClass("border-l")
    expect(screen.getByTestId("agent-active-run")).not.toHaveClass(
      "rounded-[12px]",
    )
    expect(screen.getByRole("status")).toHaveTextContent("Running")
    expect(screen.getByText("Using tools")).toBeInTheDocument()
    expect(screen.getByText("1 of 3 actions finished")).toBeInTheDocument()
    expect(screen.getByRole("progressbar", { name: "Tool progress" })).toHaveAttribute(
      "aria-valuenow",
      "33",
    )

    expect(
      screen.getByRole("region", { name: "Thinking summary" }),
    ).toHaveTextContent("inspect the workflow and parameters together")
    expect(screen.getByRole("region", { name: "Response" })).toHaveTextContent(
      "I found the workflow",
    )

    expect(
      screen.getByRole("button", { name: "2 tools running in parallel" }),
    ).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("Validate workflow inputs")).toBeInTheDocument()
  })

  it("keeps failed live tool details visible by default", () => {
    const failedRun = activeRun()
    failedRun.assistant_draft = null
    failedRun.tool_progress = [
      {
        ...baseTool,
        status: "failed",
        error: "Command exited with status 1",
        output_summary: null,
        public_details: [
          {
            id: "error",
            kind: "error",
            label: null,
            value: "Command exited with status 1",
            format: "text",
            copyable: false,
            truncated: false,
            redacted: false,
          },
        ],
      },
    ]

    renderWithProviders(<ActiveRun activeRun={failedRun} />)

    expect(screen.getByText("Error")).toBeInTheDocument()
    expect(screen.getByText("Command exited with status 1")).toBeInTheDocument()
  })
})
