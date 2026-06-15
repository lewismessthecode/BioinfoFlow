import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTranscript } from "@/components/bioinfoflow/agent-runtime/agent-transcript"
import type { AgentRuntimeTimelineEntry } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      pendingResponse: "Working on it...",
      thinking: "Thinking",
      toolCalls: "Tool calls",
      "turnStatus.queued": "Queued",
      "turnStatus.running": "Working",
      "turnStatus.waiting_user": "Waiting for you",
      "turnStatus.waiting_approval": "Needs approval",
      "turnStatus.completed": "Done",
      "turnStatus.failed": "Failed",
      "turnStatus.cancelled": "Cancelled",
    }
    return labels[key] ?? key
  },
}))

const baseTimelineEntry: AgentRuntimeTimelineEntry = {
  turn: {
    id: "turn-1",
    session_id: "session-1",
    project_id: null,
    workspace_id: "workspace-1",
    user_id: "user-1",
    input_text: "Summarize the run log.",
    input_parts: null,
    status: "completed",
    model_selection: null,
    model_profile_snapshot: null,
    final_text: null,
    token_usage: null,
    termination_reason: null,
    loop_state: null,
    iteration_count: 1,
    budget_snapshot: null,
    interrupt_requested_at: null,
    error_code: null,
    error_message: null,
    created_at: "2026-06-10T00:00:00Z",
    updated_at: "2026-06-10T00:00:00Z",
    started_at: "2026-06-10T00:00:01Z",
    completed_at: "2026-06-10T00:00:02Z",
  },
  assistant: {
    messageId: "message-1",
    text: "",
    status: "completed",
    errorMessage: null,
    thinking: null,
    toolCalls: [],
  },
}

describe("AgentTranscript", () => {
  it("renders assistant markdown content through the shared markdown renderer", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            assistant: {
              ...baseTimelineEntry.assistant,
              text: "# Summary\n- First finding\n- Second finding\n\nUse `nextflow log`.",
            },
          },
        ]}
      />,
    )

    expect(
      screen.getByRole("heading", { name: "Summary", level: 1 }),
    ).toBeInTheDocument()
    expect(screen.getByText("First finding")).toBeInTheDocument()
    expect(screen.getByText("Second finding")).toBeInTheDocument()
    expect(screen.getByText("nextflow log")).toBeInTheDocument()
  })

  it("shows the projected running status instead of queued once output is streaming", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            turn: {
              ...baseTimelineEntry.turn,
              status: "running",
            },
            assistant: {
              ...baseTimelineEntry.assistant,
              status: "streaming",
              text: "Streaming answer",
            },
          },
        ]}
      />,
    )

    expect(screen.getByText("Working")).toBeInTheDocument()
    expect(screen.queryByText("Queued")).not.toBeInTheDocument()
  })

  it("renders tool calls as collapsed compact rows by default", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            assistant: {
              ...baseTimelineEntry.assistant,
              toolCalls: [
                {
                  callId: "call-1",
                  name: "glob",
                  status: "completed",
                  index: 0,
                  arguments: { pattern: "**/*.wdl" },
                  argumentsDelta: null,
                },
                {
                  callId: "call-2",
                  name: "files__read",
                  status: "completed",
                  index: 1,
                  arguments: { path: "/app/workflow.wdl" },
                  argumentsDelta: null,
                },
              ],
            },
          },
        ]}
      />,
    )

    expect(screen.getByText("Tool calls")).toBeInTheDocument()
    expect(screen.getByText("glob")).toBeInTheDocument()
    expect(screen.getByText("files__read")).toBeInTheDocument()
    const rows = screen.getAllByTestId("agent-tool-call-row")
    expect(rows).toHaveLength(2)
    expect(rows[0]).not.toHaveAttribute("open")
    expect(screen.queryByText(/workflow\.wdl/)).not.toBeInTheDocument()
  })
})
