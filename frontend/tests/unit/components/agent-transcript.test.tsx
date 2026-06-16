import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTranscript } from "@/components/bioinfoflow/agent-runtime/agent-transcript"
import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"
import type {
  AgentRuntimeArtifact,
  AgentRuntimeEvent,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      pendingResponse: "Working on it...",
      thinking: "Thinking",
      approve: "Approve",
      reject: "Reject",
      "sidecar.needsDecision": "Needs your decision",
      "approval.state.approved": "Approved, resuming",
      "approval.state.answered": "Answer submitted, resuming",
      "approval.state.rejected": "Rejected",
      "approval.state.failed": "Failed",
      "approval.state.cancelled": "Cancelled",
      "ask.title": "The agent needs your input",
      "ask.submit": "Submit answer",
      "progress.tasks": "Tasks",
      "progress.empty": "No tasks yet",
      "plan.reviewTitle": "Review the plan",
      "plan.approveAndAct": "Approve & act",
      "plan.keepPlanning": "Keep planning",
      "plan.status.pending": "Pending",
      "activity.groups.read": "Read project structure",
      "activity.groups.run": "Submit run",
      "activity.groups.verify": "Verify results",
      "activity.summary.read": "Read 2 sources",
      "activity.summary.run": "Submitted 1 run",
      "activity.summary.verify": "Verified 1 check",
      "activity.status.failed": "Failed",
      "activity.status.cancelled": "Cancelled",
      "activity.status.rejected": "Rejected",
      "activity.status.waiting": "Waiting",
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
      scrollToBottom: "Jump to latest",
    }
    return labels[key] ?? key
  },
}))

const baseTurn: AgentRuntimeTurn = {
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

function event(
  id: string,
  seq: number,
  type: string,
  payload: Record<string, unknown> = {},
): AgentRuntimeEvent {
  return {
    id,
    session_id: "session-1",
    turn_id: "turn-1",
    seq,
    type,
    payload,
    visibility: "user",
    schema_version: 1,
    created_at: `2026-06-10T00:00:${String(seq).padStart(2, "0")}Z`,
    updated_at: `2026-06-10T00:00:${String(seq).padStart(2, "0")}Z`,
  }
}

function renderTranscript({
  turn = baseTurn,
  events = [],
  artifacts = [],
  onDecision,
}: {
  turn?: AgentRuntimeTurn
  events?: AgentRuntimeEvent[]
  artifacts?: AgentRuntimeArtifact[]
  onDecision?: Parameters<typeof AgentTranscript>[0]["onDecision"]
} = {}) {
  return render(
    <AgentTranscript
      timeline={buildAgentRuntimeTimeline([turn], events)}
      artifacts={artifacts}
      events={events}
      onDecision={onDecision}
    />,
  )
}

function textTimeline(text: string) {
  return buildAgentRuntimeTimeline(
    [baseTurn],
    [
      event("event-text", 1, "assistant.text.completed", {
        message_id: "message-1",
        content: text,
      }),
    ],
  )
}

describe("AgentTranscript", () => {
  it("renders assistant markdown content through the shared markdown renderer", () => {
    renderTranscript({
      turn: {
        ...baseTurn,
        final_text: "# Summary\n- First finding\n- Second finding\n\nUse `nextflow log`.",
      },
    })

    expect(screen.getByRole("heading", { name: "Summary", level: 1 })).toBeInTheDocument()
    expect(screen.getByText("First finding")).toBeInTheDocument()
    expect(screen.getByText("Second finding")).toBeInTheDocument()
    expect(screen.getByText("nextflow log")).toBeInTheDocument()
  })

  it("keeps the transcript pinned to the bottom when new content streams in", () => {
    const { rerender } = render(<AgentTranscript timeline={textTimeline("First chunk")} />)
    const scroller = screen.getByTestId("agent-transcript-scroll")
    Object.defineProperties(scroller, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 260 },
      scrollTop: { configurable: true, writable: true, value: 60 },
    })

    act(() => {
      fireEvent.scroll(scroller)
    })

    Object.defineProperty(scroller, "scrollHeight", {
      configurable: true,
      value: 420,
    })

    rerender(
      <AgentTranscript timeline={textTimeline("First chunk\n\nSecond chunk")} />,
    )

    expect(scroller.scrollTop).toBe(220)
  })

  it("pauses bottom following after the user scrolls up and resumes from the control", () => {
    const { rerender } = render(<AgentTranscript timeline={textTimeline("First chunk")} />)
    const scroller = screen.getByTestId("agent-transcript-scroll")
    Object.defineProperties(scroller, {
      clientHeight: { configurable: true, value: 200 },
      scrollHeight: { configurable: true, value: 420 },
      scrollTop: { configurable: true, writable: true, value: 40 },
    })

    act(() => {
      fireEvent.scroll(scroller)
    })

    rerender(
      <AgentTranscript timeline={textTimeline("First chunk\n\nSecond chunk")} />,
    )

    expect(scroller.scrollTop).toBe(40)

    fireEvent.click(screen.getByRole("button", { name: "Jump to latest" }))

    expect(scroller.scrollTop).toBe(220)
  })

  it("shows the projected running status instead of queued once output is streaming", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-text", 1, "assistant.text.delta", {
          message_id: "message-1",
          delta: "Streaming answer",
        }),
      ],
    })

    expect(screen.getByText("Working")).toBeInTheDocument()
    expect(screen.queryByText("Queued")).not.toBeInTheDocument()
    expect(screen.getByText("Streaming answer")).toBeInTheDocument()
  })

  it("renders tool activity as collapsed narrative groups by default", () => {
    renderTranscript({
      events: [
        event("event-call-1", 1, "assistant.tool_call.completed", {
          call_id: "call-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
        event("event-call-2", 2, "assistant.tool_call.completed", {
          call_id: "call-2",
          name: "files__read",
          status: "completed",
          arguments: { path: "/app/workflow.wdl" },
          index: 1,
        }),
      ],
    })

    expect(screen.getByText("Read project structure")).toBeInTheDocument()
    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.queryByText("glob")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Read project structure/ }))

    expect(screen.getByText("glob")).toBeInTheDocument()
    expect(screen.getByText("files__read")).toBeInTheDocument()
    expect(screen.getAllByTestId("agent-tool-activity-row")).toHaveLength(2)
    expect(screen.getAllByText(/workflow\.wdl/).length).toBeGreaterThan(0)
  })

  it("renders failed tool activity as collapsed narrative groups by default", () => {
    renderTranscript({
      events: [
        event("event-failed", 1, "action.failed", {
          action_id: "action-1",
          name: "runs__submit",
          error_message: "Image quay.io/example/missing:tag was not found",
        }),
      ],
    })

    expect(screen.getByText("Submit run")).toBeInTheDocument()
    expect(screen.getByText("Failed")).toBeInTheDocument()
    expect(
      screen.queryByText("Image quay.io/example/missing:tag was not found"),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Submit run/ }))

    expect(
      screen.getByText("Image quay.io/example/missing:tag was not found"),
    ).toBeInTheDocument()
  })

  it("renders exit_plan_mode plans as inline conversation decisions", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "waiting_approval", final_text: null },
      events: [
        event("event-plan", 1, "action.waiting_decision", {
          action_id: "action-plan",
          name: "exit_plan_mode",
          interaction: {
            kind: "plan_approval",
            plan: "1. Inspect files\n2. Apply the fix",
          },
        }),
      ],
    })

    expect(screen.getByTestId("inline-plan-card")).toBeInTheDocument()
    expect(screen.getByText("Review the plan")).toBeInTheDocument()
    expect(screen.getByText("Inspect files", { exact: false })).toBeInTheDocument()
  })

  it("does not render todo_list artifacts inside the transcript stream", () => {
    renderTranscript({ artifacts: [todoArtifact] })

    expect(screen.queryByTestId("inline-todo-card")).not.toBeInTheDocument()
    expect(screen.queryByText("Editing")).not.toBeInTheDocument()
  })

  it("renders inline approval cards with decision buttons", () => {
    const onDecision = vi.fn()
    renderTranscript({
      turn: { ...baseTurn, status: "waiting_approval", final_text: null },
      events: [
        event("event-approval", 1, "action.waiting_decision", {
          action_id: "action-1",
          name: "bash",
          risk_level: "act_high",
          input_preview: "rm build/",
        }),
      ],
      onDecision,
    })

    expect(screen.getByTestId("inline-approval-card")).toBeInTheDocument()
    expect(screen.getByText("Needs your decision")).toBeInTheDocument()
    expect(screen.getByText("rm build/")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Approve" }))
    expect(onDecision).toHaveBeenCalledWith("action-1", "approve")
  })

  it("does not render cancelled waiting decisions as pending approvals", () => {
    renderTranscript({
      events: [
        event("event-approval", 1, "action.waiting_decision", {
          action_id: "action-1",
          name: "bash",
        }),
        event("event-cancelled", 2, "action.cancelled", { action_id: "action-1" }),
      ],
    })

    expect(screen.getAllByText("Cancelled").length).toBeGreaterThan(0)
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
  })

  it("renders inline ask-user decisions with answer submission", () => {
    const onDecision = vi.fn()
    renderTranscript({
      turn: { ...baseTurn, status: "waiting_user", final_text: null },
      events: [
        event("event-ask", 1, "action.waiting_decision", {
          action_id: "action-ask",
          name: "ask_user",
          interaction: {
            kind: "user_input",
            questions: [
              {
                header: "Genome",
                question: "Which reference genome?",
                multiSelect: false,
                options: [
                  { label: "hg38", description: "Human GRCh38" },
                  { label: "mm10", description: "Mouse mm10" },
                ],
              },
            ],
          },
        }),
      ],
      onDecision,
    })

    expect(screen.getByTestId("inline-ask-user-card")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /hg38/ }))
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }))

    expect(onDecision).toHaveBeenCalledWith("action-ask", "answer", {
      answer: { Genome: "hg38" },
    })
  })

  it("keeps text, tool calls, and later text in segment order", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-text-1", 1, "assistant.text.completed", {
          message_id: "message-1",
          content: "I am checking the workflow registry before reading files.",
        }),
        event("event-tool", 2, "assistant.tool_call.completed", {
          message_id: "message-1",
          call_id: "call-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
        event("event-text-2", 3, "assistant.text.completed", {
          message_id: "message-2",
          content: "The workflow file is present.",
        }),
      ],
    })

    expect(
      screen.getByText("I am checking the workflow registry before reading files."),
    ).toBeInTheDocument()
    expect(screen.getByText("Read project structure")).toBeInTheDocument()
    expect(screen.getByText("The workflow file is present.")).toBeInTheDocument()
    expect(screen.queryByText("Working on it...")).not.toBeInTheDocument()
  })

  it("keeps thinking content expanded when tool calls arrive later", () => {
    renderTranscript({
      events: [
        event("event-thinking", 1, "assistant.thinking.summary", {
          message_id: "message-1",
          content: "I need to inspect the workflow files before answering.",
        }),
        event("event-tool", 2, "assistant.tool_call.completed", {
          message_id: "message-1",
          call_id: "call-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
      ],
    })

    const thinkingPanel = screen.getByText("Thinking").closest("details")
    expect(thinkingPanel).toHaveAttribute("open")
    expect(
      screen.getByText("I need to inspect the workflow files before answering."),
    ).toBeVisible()
  })

  it("keeps assistant text visible and shows a separate failed turn banner", () => {
    renderTranscript({
      turn: {
        ...baseTurn,
        status: "failed",
        final_text: null,
        error_message: "files__read failed",
      },
      events: [
        event("event-text", 1, "assistant.text.completed", {
          message_id: "message-1",
          content: "Now let me try another way.",
        }),
        event("event-failed", 2, "turn.failed", {
          error_message: "files__read failed",
        }),
      ],
    })

    const followUp = screen.getByText("Now let me try another way.")
    expect(followUp.closest(".text-destructive")).toBeNull()
    expect(screen.getByText("files__read failed")).toBeInTheDocument()
  })
})
