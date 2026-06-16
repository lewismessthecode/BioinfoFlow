import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTranscript } from "@/components/bioinfoflow/agent-runtime/agent-transcript"
import type { AgentRuntimeArtifact, AgentRuntimeTimelineEntry } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      pendingResponse: "Working on it...",
      thinking: "Thinking",
      toolCalls: "Tool calls",
      "progress.tasks": "Tasks",
      "plan.reviewTitle": "Review the plan",
      "plan.status.pending": "Pending",
      "activity.groups.read": "Read project structure",
      "activity.groups.verify": "Verify results",
      "activity.summary.read": "Read 2 sources",
      "activity.summary.verify": "Verified 1 check",
      "activity.status.failed": "Failed",
      "activity.details.input": "Input",
      "activity.details.arguments": "Arguments",
      "activity.details.output": "Output",
      "activity.details.exitCode": "Exit code",
      "activity.details.error": "Error",
      "activity.details.files": "Files",
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
  activities: [],
  activityGroups: [],
  inlinePlans: [],
}

const todoArtifact: AgentRuntimeArtifact = {
  id: "artifact-todo",
  session_id: "session-1",
  turn_id: "turn-1",
  action_id: "action-todo",
  type: "todo_list",
  title: "Tasks",
  summary: null,
  payload: {
    todos: [
      { content: "Read the code", status: "completed" },
      { content: "Make the change", status: "in_progress", activeForm: "Editing" },
    ],
  },
  file_path: null,
  resource_ref: null,
  created_at: "2026-06-10T00:00:03Z",
  updated_at: "2026-06-10T00:00:03Z",
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

  it("renders tool activity as collapsed narrative groups by default", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            activityGroups: [
              {
                id: "read-0",
                kind: "read",
                status: "completed",
                activities: [
                  {
                    id: "call-1",
                    callId: "call-1",
                    actionId: null,
                    name: "glob",
                    status: "completed",
                    arguments: { pattern: "**/*.wdl" },
                    relatedFiles: [],
                  },
                  {
                    id: "call-2",
                    callId: "call-2",
                    actionId: null,
                    name: "files__read",
                    status: "completed",
                    arguments: { path: "/app/workflow.wdl" },
                    relatedFiles: ["/app/workflow.wdl"],
                  },
                ],
              },
            ],
          },
        ]}
      />,
    )

    expect(screen.getByText("Read project structure")).toBeInTheDocument()
    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.queryByText("glob")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Read project structure/ }))

    expect(screen.getByText("glob")).toBeInTheDocument()
    expect(screen.getByText("files__read")).toBeInTheDocument()
    expect(screen.getAllByTestId("agent-tool-activity-row")).toHaveLength(2)
    expect(screen.getAllByText(/workflow\.wdl/).length).toBeGreaterThan(0)
  })

  it("renders exit_plan_mode plans as inline conversation cards", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            inlinePlans: [
              {
                actionId: "action-plan",
                plan: "1. Inspect files\n2. Apply the fix",
                status: "pending",
              },
            ],
          },
        ]}
      />,
    )

    expect(screen.getByTestId("inline-plan-card")).toBeInTheDocument()
    expect(screen.getByText("Review the plan")).toBeInTheDocument()
    expect(screen.getByText("Inspect files", { exact: false })).toBeInTheDocument()
  })

  it("renders todo_list artifacts as inline progress cards", () => {
    render(<AgentTranscript timeline={[baseTimelineEntry]} artifacts={[todoArtifact]} />)

    expect(screen.getByTestId("inline-todo-card")).toBeInTheDocument()
    expect(screen.getByText("Tasks")).toBeInTheDocument()
    expect(screen.getByText("Read the code")).toBeInTheDocument()
    expect(screen.getByText("Editing")).toBeInTheDocument()
  })

  it("keeps streamed assistant text visible after later tool calls", () => {
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
              text: "I am checking the workflow registry before reading files.",
            },
            activityGroups: [
              {
                id: "read-0",
                kind: "read",
                status: "completed",
                activities: [
                  {
                    id: "call-1",
                    callId: "call-1",
                    actionId: null,
                    name: "glob",
                    status: "completed",
                    arguments: { pattern: "**/*.wdl" },
                    relatedFiles: [],
                  },
                ],
              },
            ],
          },
        ]}
      />,
    )

    expect(
      screen.getByText("I am checking the workflow registry before reading files."),
    ).toBeInTheDocument()
    expect(screen.getByText("Read project structure")).toBeInTheDocument()
    expect(screen.queryByText("glob")).not.toBeInTheDocument()
    expect(screen.queryByText("Working on it...")).not.toBeInTheDocument()
  })

  it("keeps thinking content expanded when tool calls arrive later", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            assistant: {
              ...baseTimelineEntry.assistant,
              thinking: {
                content: "I need to inspect the workflow files before answering.",
                isComplete: true,
              },
              toolCalls: [
                {
                  callId: "call-1",
                  name: "glob",
                  status: "completed",
                  index: 0,
                  arguments: { pattern: "**/*.wdl" },
                  argumentsDelta: null,
                },
              ],
            },
          },
        ]}
      />,
    )

    const thinkingPanel = screen.getByText("Thinking").closest("details")
    expect(thinkingPanel).toHaveAttribute("open")
    expect(
      screen.getByText("I need to inspect the workflow files before answering."),
    ).toBeVisible()
  })

  it("does not color normal assistant follow-up text as destructive after a failed tool", () => {
    render(
      <AgentTranscript
        timeline={[
          {
            ...baseTimelineEntry,
            turn: {
              ...baseTimelineEntry.turn,
              status: "failed",
              error_message: "files__read failed",
            },
            assistant: {
              ...baseTimelineEntry.assistant,
              status: "failed",
              text: "Now let me try another way.",
              errorMessage: "files__read failed",
            },
          },
        ]}
      />,
    )

    const followUp = screen.getByText("Now let me try another way.")
    expect(followUp.closest(".text-destructive")).toBeNull()
    expect(screen.queryByText("files__read failed")).not.toBeInTheDocument()
  })
})
