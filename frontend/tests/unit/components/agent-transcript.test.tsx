import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTranscript } from "@/components/bioinfoflow/agent-runtime/agent-transcript"
import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"
import type {
  AgentRuntimeArtifact,
  AgentRuntimeEvent,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const labels: Record<string, string> = {
      pendingResponse: "Working on it...",
      recentActivityWindow: "Showing recent activity",
      thinking: "Thinking",
      "statusLine.thinking": "Thinking...",
      "statusLine.running": "Working...",
      "responseActions.copy": "Copy response",
      "responseActions.retry": "Retry response",
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
      "ask.customLabel": "Custom answer",
      "ask.customPlaceholder": "Tell Bioinfoflow what to use",
      "ask.recommended": "Recommended",
      "ask.answerLabel": "Answer",
      "ask.rejectQuestion": "Reject question",
      "progress.tasks": "Tasks",
      "progress.empty": "No tasks yet",
      "plan.reviewTitle": "Review the plan",
      "plan.approveAndAct": "Approve & act",
      "plan.keepPlanning": "Keep planning",
      "plan.status.pending": "Pending",
      "activity.groups.search": "Searched web",
      "activity.groups.read": "Read data",
      "activity.groups.command": "Run commands",
      "activity.groups.write": "Create or edit files",
      "activity.groups.register": "Manage workflows",
      "activity.groups.run": "Submit run",
      "activity.groups.verify": "Verify results",
      "activity.summary.read": "Read {count} sources",
      "activity.summary.command": "Ran {count} commands",
      "activity.summary.write": "Edited {count} files",
      "activity.summary.register": "Managed {count} workflows",
      "activity.summary.run": "Submitted 1 run",
      "activity.summary.verify": "Verified 1 check",
      "activity.summary.search": "Found {count} sources",
      "activity.summary.searching": "Searching sources...",
      "activity.status.failed": "Failed",
      "activity.status.cancelled": "Cancelled",
      "activity.status.rejected": "Rejected",
      "activity.status.waiting": "Waiting",
      "activity.status.running": "Running",
      "activity.details.show": "Show details",
      "activity.details.hide": "Hide details",
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
      "sources.title": "Sources",
      "sources.open": "Open sources",
      "sources.openWithCount": "Open {count} sources",
      "sources.close": "Close sources",
      "sources.citationLabel": "Source {index}: {title}",
      "sources.count": "{count} sources",
      "sources.searchedWeb": "Searched web",
      "sources.resultCount": "{count} results",
      "sources.preview": "Source preview",
      "sources.description": "Review sources.",
      "sources.query": "Query",
      "sources.noSnippet": "No snippet available.",
      "sources.types.pubmed": "PubMed",
      "sources.types.biorxiv": "bioRxiv",
      "sources.types.web": "Web",
      "artifacts.generatedFiles": "Generated files",
      "artifacts.preview": "Preview",
      "artifacts.download": "Download",
      "artifacts.copyPath": "Copy path",
      "artifacts.pathCopied": "Path copied",
      "artifacts.types.file": "File",
      "artifacts.types.html": "HTML",
      "artifacts.types.markdown": "Markdown",
    }
    const label = labels[key] ?? key
    return label
      .replace("{count}", String(values?.count ?? "{count}"))
      .replace("{index}", String(values?.index ?? "{index}"))
      .replace("{title}", String(values?.title ?? "{title}"))
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
  onOpenArtifact,
  onDecision,
  onRetryTurn,
  eventWindowLimited = false,
}: {
  turn?: AgentRuntimeTurn
  events?: AgentRuntimeEvent[]
  artifacts?: AgentRuntimeArtifact[]
  onOpenArtifact?: (artifactId: string) => void
  onDecision?: Parameters<typeof AgentTranscript>[0]["onDecision"]
  onRetryTurn?: (turn: AgentRuntimeTurn) => void
  eventWindowLimited?: boolean
} = {}) {
  const props = {
    timeline: buildAgentRuntimeTimeline([turn], events),
    artifacts,
    onOpenArtifact,
    onDecision,
    onRetryTurn,
    eventWindowLimited,
  } as Parameters<typeof AgentTranscript>[0] & {
    onRetryTurn?: (turn: AgentRuntimeTurn) => void
  }
  return render(
    <AgentTranscript {...props} />,
  )
}

function transcriptArtifact(
  overrides: Partial<AgentRuntimeArtifact>,
): AgentRuntimeArtifact {
  return {
    id: "artifact-1",
    session_id: "session-1",
    turn_id: "turn-1",
    action_id: null,
    type: "file",
    title: "report.md",
    summary: null,
    payload: { path: "/workspace/report.md", content: "# Report" },
    file_path: "/workspace/report.md",
    resource_ref: null,
    created_at: "2026-06-10T00:00:03Z",
    updated_at: "2026-06-10T00:00:03Z",
    ...overrides,
  }
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
  it("marks long conversations when only the recent activity window is loaded", () => {
    renderTranscript({ eventWindowLimited: true })

    expect(screen.getByText("Showing recent activity")).toBeInTheDocument()
  })

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

    expect(screen.getByRole("status", { name: "Working..." })).toBeInTheDocument()
    expect(screen.queryByText("Queued")).not.toBeInTheDocument()
    expect(screen.getByText("Streaming answer")).toBeInTheDocument()
  })

  it("renders the live streaming status after the current assistant text", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-text", 1, "assistant.text.delta", {
          message_id: "message-1",
          delta: "Long streaming answer",
        }),
      ],
    })

    const text = screen.getByText("Long streaming answer")
    const status = screen.getByRole("status", { name: "Working..." })
    expect(text.compareDocumentPosition(status) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it("does not render a divider after the final transcript entry", () => {
    const secondTurn = {
      ...baseTurn,
      id: "turn-2",
      input_text: "Summarize the second run.",
    }
    render(
      <AgentTranscript
        timeline={buildAgentRuntimeTimeline(
          [baseTurn, secondTurn],
          [
            event("event-first", 1, "assistant.text.completed", {
              message_id: "message-1",
              content: "First answer",
            }),
            {
              ...event("event-second", 2, "assistant.text.completed", {
                message_id: "message-2",
                content: "Second answer",
              }),
              turn_id: "turn-2",
            },
          ],
        )}
      />,
    )

    expect(screen.getByText("First answer").closest("article")).toHaveClass("border-b")
    expect(screen.getByText("Second answer").closest("article")).not.toHaveClass("border-b")
  })

  it("keeps blocked waiting turns on precise status labels", () => {
    const { rerender } = renderTranscript({
      turn: { ...baseTurn, status: "waiting_approval", final_text: null },
      events: [],
    })

    expect(screen.getByText("Needs approval")).toBeInTheDocument()
    expect(screen.queryByRole("status", { name: "Working..." })).not.toBeInTheDocument()

    rerender(
      <AgentTranscript
        timeline={buildAgentRuntimeTimeline(
          [{ ...baseTurn, status: "waiting_user", final_text: null }],
          [],
        )}
      />,
    )

    expect(screen.getByText("Waiting for you")).toBeInTheDocument()
    expect(screen.queryByRole("status", { name: "Working..." })).not.toBeInTheDocument()
  })

  it("does not show live status for completed turns with stale streaming events", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "completed", final_text: null },
      events: [
        event("event-text", 1, "assistant.text.delta", {
          message_id: "message-1",
          delta: "The final answer is already visible.",
        }),
      ],
    })

    expect(screen.getByText("The final answer is already visible.")).toBeInTheDocument()
    expect(screen.getByTestId("assistant-response-actions")).toBeInTheDocument()
    expect(screen.queryByRole("status", { name: "Working..." })).not.toBeInTheDocument()
  })

  it("shows copy and retry actions after completed assistant output", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    const clipboard = { writeText }
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: clipboard,
    })
    const onRetryTurn = vi.fn()
    renderTranscript({
      events: [
        event("event-text", 1, "assistant.text.completed", {
          message_id: "message-1",
          content: "The files look ready.",
        }),
      ],
      onRetryTurn,
    })

    fireEvent.click(screen.getByRole("button", { name: "Copy response" }))
    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith("The files look ready.")
    })

    fireEvent.click(screen.getByRole("button", { name: "Retry response" }))
    expect(onRetryTurn).toHaveBeenCalledWith(baseTurn)
  })

  it("does not show completed response actions while the turn is running", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-text", 1, "assistant.text.delta", {
          message_id: "message-1",
          delta: "Still streaming",
        }),
      ],
    })

    expect(screen.queryByRole("button", { name: "Copy response" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Retry response" })).not.toBeInTheDocument()
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

    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.queryByText("glob")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Read 2 sources/ }))

    expect(screen.getByText("glob")).toBeInTheDocument()
    expect(screen.getByText("files__read")).toBeInTheDocument()
    expect(screen.getAllByTestId("agent-tool-activity-row")).toHaveLength(2)
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument()

    const detailsButton = screen.getAllByRole("button", { name: /Show details/ })[1]
    expect(detailsButton).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(detailsButton)

    expect(detailsButton).toHaveAttribute("aria-expanded", "true")
    expect(screen.getByText("Arguments")).toBeInTheDocument()
    expect(screen.getAllByText(/workflow\.wdl/).length).toBeGreaterThan(0)
  })

  it("classifies workflow list and source lookups as reads, not workflow registration", () => {
    renderTranscript({
      events: [
        event("event-workflow-list", 1, "assistant.tool_call.completed", {
          call_id: "call-workflow-list",
          name: "workflows.list",
          status: "completed",
          arguments: { project_id: "project-1" },
          index: 0,
        }),
        event("event-workflow-source", 2, "assistant.tool_call.completed", {
          call_id: "call-workflow-source",
          name: "workflows.source",
          status: "completed",
          arguments: { workflow_id: "workflow-1" },
          index: 1,
        }),
      ],
    })

    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.queryByText("Manage workflows")).not.toBeInTheDocument()
  })

  it("classifies real platform read, workflow, command, and verify tools into coarse groups", () => {
    renderTranscript({
      events: [
        event("event-runs-logs", 1, "assistant.tool_call.completed", {
          call_id: "call-runs-logs",
          name: "runs.logs",
          status: "completed",
          arguments: { run_id: "run-1" },
          index: 0,
        }),
        event("event-runs-outputs", 2, "assistant.tool_call.completed", {
          call_id: "call-runs-outputs",
          name: "runs.outputs",
          status: "completed",
          arguments: { run_id: "run-1" },
          index: 1,
        }),
        event("event-workflows-bind", 3, "assistant.tool_call.completed", {
          call_id: "call-workflows-bind",
          name: "projects.workflows.bind",
          status: "completed",
          arguments: { project_id: "project-1", workflow_id: "workflow-1" },
          index: 2,
        }),
        event("event-image-build", 4, "assistant.tool_call.completed", {
          call_id: "call-image-build",
          name: "images.build",
          status: "completed",
          arguments: { dockerfile: "Dockerfile" },
          index: 3,
        }),
        event("event-mixed-verify", 5, "action.completed", {
          action_id: "action-mixed-verify",
          name: "bash",
          input_preview: "rg failing-test && bun run test",
          result: { exit_code: 0, stdout: "ok" },
        }),
      ],
    })

    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.getByText("Managed 1 workflows")).toBeInTheDocument()
    expect(screen.getByText("Ran 1 commands")).toBeInTheDocument()
    expect(screen.getByText("Verified 1 check")).toBeInTheDocument()
    expect(screen.queryByText("activity.groups.other")).not.toBeInTheDocument()
  })

  it("uses tool-call arguments as fallback hints for bash activity classification", () => {
    renderTranscript({
      events: [
        event("event-bash-verify", 1, "assistant.tool_call.completed", {
          call_id: "call-bash-verify",
          name: "bash",
          status: "completed",
          arguments: { command: "bun run test" },
          index: 0,
        }),
        event("event-bash-write", 2, "assistant.tool_call.completed", {
          call_id: "call-bash-write",
          name: "bash",
          status: "completed",
          arguments: { command: "rm build/" },
          index: 1,
        }),
      ],
    })

    expect(screen.getByText("Verified 1 check")).toBeInTheDocument()
    expect(screen.getByText("Edited 1 files")).toBeInTheDocument()
    expect(screen.queryByText("Ran 1 commands")).not.toBeInTheDocument()
  })

  it("compacts same-category tool calls inside one contiguous tool burst", () => {
    renderTranscript({
      events: [
        event("event-glob-1", 1, "assistant.tool_call.completed", {
          call_id: "call-glob-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
        event("event-bash-1", 2, "action.completed", {
          action_id: "action-bash-1",
          name: "bash",
          input_preview: "docker inspect minibwa:1.0",
          result: { exit_code: 0, stdout: "ok" },
        }),
        event("event-source", 3, "assistant.tool_call.completed", {
          call_id: "call-source",
          name: "workflows.source",
          status: "completed",
          arguments: { workflow_id: "workflow-1" },
          index: 1,
        }),
        event("event-bash-2", 4, "action.completed", {
          action_id: "action-bash-2",
          name: "bash",
          input_preview: "docker run --rm minibwa:1.0 --help",
          result: { exit_code: 0, stdout: "usage" },
        }),
        event("event-glob-2", 5, "assistant.tool_call.completed", {
          call_id: "call-glob-2",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.json" },
          index: 2,
        }),
      ],
    })

    expect(screen.getAllByTestId("agent-activity-group")).toHaveLength(2)
    expect(screen.getByText("Read 3 sources")).toBeInTheDocument()
    expect(screen.getByText("Ran 2 commands")).toBeInTheDocument()
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

    expect(screen.getByText("Submitted 1 run")).toBeInTheDocument()
    expect(screen.getByText("Failed")).toBeInTheDocument()
    expect(
      screen.queryByText("Image quay.io/example/missing:tag was not found"),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Submitted 1 run/ }))

    expect(
      screen.queryByText("Image quay.io/example/missing:tag was not found"),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Show details/ }))

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

  it("does not render todo artifacts inside the transcript stream", () => {
    renderTranscript()

    expect(screen.queryByTestId("inline-todo-card")).not.toBeInTheDocument()
    expect(screen.queryByText("Editing")).not.toBeInTheDocument()
  })

  it("renders generated file cards for the matching assistant turn only", () => {
    const onOpenArtifact = vi.fn()
    const otherTurnArtifact = transcriptArtifact({
      id: "other-file",
      turn_id: "turn-2",
      title: "other.md",
      file_path: "/workspace/other.md",
      payload: { path: "/workspace/other.md", content: "# Other" },
    })

    renderTranscript({
      artifacts: [
        transcriptArtifact({
          id: "html-1",
          type: "html",
          title: "/workspace/index.html",
          summary: "Wrote 13166 bytes",
          file_path: "/workspace/index.html",
          payload: { path: "/workspace/index.html", content: "<h1>Report</h1>" },
        }),
        transcriptArtifact({
          id: "command-1",
          type: "command",
          title: "shell output",
          payload: { stdout: "index.html" },
          file_path: null,
        }),
        transcriptArtifact({
          id: "run-1",
          type: "run",
          title: "Run record",
          file_path: "/workspace/run-output.txt",
        }),
        otherTurnArtifact,
      ],
      onOpenArtifact,
    })

    const cards = screen.getByTestId("generated-file-cards")
    expect(within(cards).getByText("Generated files")).toBeInTheDocument()
    expect(within(cards).getByText("index.html")).toBeInTheDocument()
    expect(within(cards).getByText("Wrote 13166 bytes")).toBeInTheDocument()
    expect(within(cards).queryByText("shell output")).not.toBeInTheDocument()
    expect(within(cards).queryByText("Run record")).not.toBeInTheDocument()
    expect(within(cards).queryByText("other.md")).not.toBeInTheDocument()

    fireEvent.click(within(cards).getByRole("button", { name: "Preview index.html" }))

    expect(onOpenArtifact).toHaveBeenCalledWith("html-1")
  })

  it("renders inline approval cards with decision buttons", () => {
    const onDecision = vi.fn(() => new Promise<void>(() => {}))
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
    expect(screen.getAllByText("rm build/").length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole("button", { name: "Approve" }))
    expect(onDecision).toHaveBeenCalledWith("action-1", "approve")
  })

  it("renders completed approvals as lightweight transcript rows", () => {
    renderTranscript({
      events: [
        event("event-approval", 1, "action.waiting_decision", {
          action_id: "action-1",
          name: "runs.submit",
          risk_level: "act_low",
          input_preview: "Submit wf-rnaseq-quant-mini with paired FASTQ inputs.",
        }),
        event("event-completed", 2, "action.completed", {
          action_id: "action-1",
          name: "runs.submit",
          result: { status: "submitted" },
        }),
      ],
    })

    const summary = screen.getByTestId("inline-approval-summary")
    expect(summary).toBeInTheDocument()
    expect(summary).not.toHaveClass("border")
    expect(screen.queryByTestId("inline-approval-card")).not.toBeInTheDocument()
    expect(screen.getByText("runs.submit")).toBeInTheDocument()
    expect(summary.querySelector("pre")).not.toHaveClass("bg-muted/25")
    expect(summary.querySelector("pre")).not.toHaveClass("rounded-md")
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
    const onDecision = vi.fn(() => new Promise<void>(() => {}))
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
                  { label: "hg38", description: "Human GRCh38", recommended: true },
                  { label: "mm10", description: "Mouse mm10" },
                ],
              },
            ],
          },
        }),
      ],
      onDecision,
    })

    expect(screen.getByTestId("inline-ask-user-card")).toHaveAttribute("tabindex", "-1")
    expect(screen.getByText("Recommended")).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText("Tell Bioinfoflow what to use"), {
      target: { value: "T2T-CHM13" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }))

    expect(onDecision).toHaveBeenCalledWith("action-ask", "answer", {
      answer: { Genome: "T2T-CHM13" },
    })
  })

  it("renders answered ask-user decisions as grayscale transcript content", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-ask", 1, "action.waiting_decision", {
          action_id: "action-ask",
          name: "ask_user",
          input_preview:
            '{"questions":[{"question":"flaky_count \\u63a7\\u5236 FLALY"}]}',
          interaction: {
            kind: "user_input",
            questions: [
              {
                header: "Retry",
                question: "flaky_count 控制 FLAKY 任务重试次数吗？",
                multiSelect: false,
                options: [
                  { label: "2", description: "Retry twice", recommended: true },
                  { label: "1", description: "Retry once" },
                ],
              },
            ],
          },
        }),
        event("event-answer", 2, "action.decision_recorded", {
          action_id: "action-ask",
          decision: "answer",
          answer: { Retry: "2" },
        }),
        event("event-completed", 3, "action.completed", {
          action_id: "action-ask",
          name: "ask_user",
          result: { answers: { Retry: "2" } },
        }),
      ],
    })

    expect(screen.getByTestId("inline-ask-user-card")).toBeInTheDocument()
    expect(screen.getByText("flaky_count 控制 FLAKY 任务重试次数吗？")).toBeInTheDocument()
    expect(screen.getByText("Answer")).toBeInTheDocument()
    expect(screen.getAllByText("2").length).toBeGreaterThan(0)
    expect(screen.queryByText(/\\u63a7/)).not.toBeInTheDocument()
    expect(screen.queryByTestId("inline-approval-card")).not.toBeInTheDocument()
  })

  it("expands active tool groups by default and collapses completed groups", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-running", 1, "action.started", {
          action_id: "action-running",
          name: "bash",
          input_preview: "bun run test",
        }),
        event("event-completed", 2, "assistant.tool_call.completed", {
          call_id: "call-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
      ],
    })

    expect(screen.getByText("Verified 1 check")).toBeInTheDocument()
    expect(screen.getByText("bash")).toBeInTheDocument()
    expect(screen.getByText("Read 1 sources")).toBeInTheDocument()
    expect(screen.queryByText("glob")).not.toBeInTheDocument()
  })

  it("keeps activity details collapsed until the user expands them", () => {
    renderTranscript({
      events: [
        event("event-tool", 1, "assistant.tool_call.completed", {
          message_id: "message-1",
          call_id: "call-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
      ],
    })

    expect(screen.getByText("Read 1 sources")).toBeInTheDocument()
    expect(screen.queryByTestId("agent-tool-activity-row")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Read 1 sources/ }))

    expect(screen.getByTestId("agent-tool-activity-row")).toBeInTheDocument()
    expect(screen.getByText("glob")).toBeInTheDocument()
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Show details/ }))

    expect(screen.getByText("Arguments")).toBeInTheDocument()
  })

  it("keeps wide transcript content inside the transcript scroller", () => {
    const longPath = `/workspace/${"very-long-directory-name-".repeat(12)}result.json`
    renderTranscript({
      events: [
        event("event-text", 1, "assistant.text.completed", {
          message_id: "message-1",
          content: `Here is the path: ${longPath}\n\n\`\`\`json\n{\"path\":\"${longPath}\"}\n\`\`\``,
        }),
      ],
    })

    expect(screen.getByTestId("agent-transcript-scroll")).toHaveClass("overflow-x-hidden")
    expect(screen.getByText(`Here is the path: ${longPath}`)).toHaveClass("break-words")
    const code = screen.getByText((content, element) =>
      element?.tagName.toLowerCase() === "code" && content.includes(longPath),
    )
    expect(code.closest("pre")).toHaveClass("overflow-x-auto")
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
    expect(screen.getByText("Read 1 sources")).toBeInTheDocument()
    expect(screen.getByText("The workflow file is present.")).toBeInTheDocument()
    expect(screen.queryByText("Working on it...")).not.toBeInTheDocument()
  })

  it("renders completed replay text only once when final text matches streamed text", () => {
    renderTranscript({
      turn: {
        ...baseTurn,
        status: "completed",
        final_text: "I am checking the workflow registry before reading files.\n\nThe workflow file is present.",
      },
      events: [
        event("event-text-1", 1, "assistant.text.delta", {
          message_id: "message-1",
          delta: "I am checking the workflow registry before reading files.",
        }),
        event("event-tool", 2, "assistant.tool_call.completed", {
          message_id: "message-1",
          call_id: "call-1",
          name: "glob",
          status: "completed",
          arguments: { pattern: "**/*.wdl" },
          index: 0,
        }),
        event("event-text-2", 3, "assistant.text.delta", {
          message_id: "message-1",
          delta: "The workflow file is present.",
        }),
      ],
    })

    expect(
      screen.getAllByText("I am checking the workflow registry before reading files."),
    ).toHaveLength(1)
    expect(screen.getAllByText("The workflow file is present.")).toHaveLength(1)
  })

  it("keeps completed thinking content available behind a disclosure", () => {
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
    expect(thinkingPanel).not.toHaveAttribute("open")
    expect(thinkingPanel).not.toHaveClass("border")
    expect(thinkingPanel).not.toHaveClass("bg-background")
    const thinkingSummary = screen.getByText("Thinking").closest("summary")
    const disclosureIcon = thinkingSummary?.querySelector("svg:last-child")
    expect(disclosureIcon).toHaveClass("opacity-0")
    fireEvent.click(screen.getByText("Thinking"))
    expect(
      screen.getByText("I need to inspect the workflow files before answering."),
    ).toBeVisible()
  })

  it("renders streaming thinking as a lightweight status line", () => {
    renderTranscript({
      turn: { ...baseTurn, status: "running", final_text: null },
      events: [
        event("event-text", 1, "assistant.text.delta", {
          message_id: "message-1",
          delta: "I am checking the server state.",
        }),
        event("event-thinking", 2, "assistant.thinking.delta", {
          message_id: "message-1",
          delta: "Comparing the local checkout.",
        }),
      ],
    })

    expect(screen.getByText("I am checking the server state.")).toBeInTheDocument()
    expect(screen.getByText("Thinking...")).toBeInTheDocument()
    expect(screen.queryByText("Comparing the local checkout.")).not.toBeInTheDocument()
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

  it("renders source-backed answers with inline citation previews and a sources drawer", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input: { query: "STAR RNA-seq aligner PubMed" },
          result: {
            query: "STAR RNA-seq aligner PubMed",
            results: [
              {
                title: "STAR: ultrafast universal RNA-seq aligner",
                url: "https://pubmed.ncbi.nlm.nih.gov/23104886/",
                snippet:
                  "STAR aligns RNA-seq reads using sequential maximum mappable seed search.",
              },
              {
                title: "Frequently Asked Questions",
                url: "https://www.biorxiv.org/about/FAQ",
                snippet: "bioRxiv distributes complete but unpublished manuscripts.",
              },
            ],
          },
        }),
        event("event-text", 2, "assistant.text.completed", {
          message_id: "message-1",
          content:
            "STAR is appropriate for splice-aware RNA-seq alignment [1](source:pubmed-star). For preprints, inspect the bioRxiv page [2](source:biorxiv-faq).",
          sources: [
            {
              id: "pubmed-star",
              title: "STAR: ultrafast universal RNA-seq aligner",
              url: "https://pubmed.ncbi.nlm.nih.gov/23104886/",
              domain: "pubmed.ncbi.nlm.nih.gov",
              snippet: "STAR aligns RNA-seq reads using sequential maximum mappable seed search.",
              sourceType: "pubmed",
              query: "STAR RNA-seq aligner PubMed",
              resultCount: 2,
            },
            {
              id: "biorxiv-faq",
              title: "Frequently Asked Questions",
              url: "https://www.biorxiv.org/about/FAQ",
              domain: "biorxiv.org",
              snippet: "bioRxiv distributes complete but unpublished manuscripts.",
              sourceType: "biorxiv",
              query: "bioRxiv FAQ preprint",
              resultCount: 2,
            },
          ],
        }),
      ],
    })

    expect(screen.getByText("Found 2 sources")).toBeInTheDocument()
    const firstCitation = screen.getByRole("button", {
      name: /Source 1: STAR: ultrafast universal RNA-seq aligner/,
    })
    expect(firstCitation).toBeInTheDocument()

    fireEvent.focus(firstCitation)
    expect(screen.getByText("Source preview")).toBeInTheDocument()
    expect(screen.getByText("STAR: ultrafast universal RNA-seq aligner")).toBeInTheDocument()
    expect(screen.getByText(/sequential maximum mappable seed/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Open 2 sources" }))
    expect(screen.getByRole("dialog", { name: "Sources" })).toBeInTheDocument()
    expect(screen.getAllByText("Searched web").length).toBeGreaterThan(0)
    expect(screen.getByText("STAR RNA-seq aligner PubMed")).toBeInTheDocument()
    expect(screen.getAllByText("2 results").length).toBeGreaterThan(0)
    expect(screen.getByRole("link", { name: /pubmed\.ncbi\.nlm\.nih\.gov/ })).toHaveAttribute(
      "href",
      "https://pubmed.ncbi.nlm.nih.gov/23104886/",
    )
  })

  it("binds answer citations to prior search results without explicit source payloads", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input: { query: "single-cell RNA-seq normalization sources" },
          result: {
            query: "single-cell RNA-seq normalization sources",
            results: [
              {
                title: "Normalization and variance stabilization of single-cell RNA-seq data",
                url: "https://pubmed.ncbi.nlm.nih.gov/31870423/",
                snippet: "Regularized negative binomial regression normalizes UMI count data.",
              },
              {
                title: "Scanpy preprocessing tutorial",
                url: "https://scanpy.readthedocs.io/en/stable/tutorials/basics/clustering.html",
                snippet: "Scanpy documents preprocessing and clustering workflows.",
              },
            ],
          },
        }),
        event("event-text", 2, "assistant.text.completed", {
          message_id: "message-1",
          content:
            "Use a model-aware normalization for UMI counts [1](source:1), then inspect Scanpy preprocessing guidance [2](source:2).",
        }),
      ],
    })

    const firstCitation = screen.getByRole("button", {
      name: /Source 1: Normalization and variance stabilization/,
    })
    expect(firstCitation).toBeInTheDocument()

    fireEvent.focus(firstCitation)
    expect(screen.getByText("Source preview")).toBeInTheDocument()
    expect(screen.getByText(/Regularized negative binomial regression/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Open 2 sources" }))
    expect(
      screen.getByRole("link", { name: /Normalization and variance stabilization/ }),
    ).toHaveAttribute("href", "https://pubmed.ncbi.nlm.nih.gov/31870423/")
    expect(screen.getAllByText("2 results").length).toBeGreaterThan(0)
  })

  it("shows a repeated prior source footer only once when later text does not cite it", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          result: {
            query: "GitLab phoenix-cli",
            results: [
              {
                title: "Phoenix CLI",
                url: "https://gitlab.genomics.cn/phoenix/phoenix-cli",
                snippet: "Phoenix CLI repository.",
              },
            ],
          },
        }),
        event("event-text-1", 2, "assistant.text.completed", {
          message_id: "message-1",
          content: "GitLab requires a signed-in session, so I will try another route.",
        }),
        event("event-text-2", 3, "assistant.text.completed", {
          message_id: "message-2",
          content: "The next step is to inspect the server checkout directly.",
        }),
      ],
    })

    expect(screen.getAllByRole("button", { name: "Open 1 sources" })).toHaveLength(1)
    expect(screen.getByText("GitLab requires a signed-in session, so I will try another route.")).toBeInTheDocument()
    expect(screen.getByText("The next step is to inspect the server checkout directly.")).toBeInTheDocument()
  })

  it("groups real backend search results by the action input preview", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input_preview: "ATAC-seq peak calling review",
          result: {
            results: [
              {
                title: "ATAC-seq Guidelines",
                url: "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4374986/",
                snippet: "ATAC-seq detects accessible chromatin.",
              },
            ],
          },
        }),
        event("event-text", 2, "assistant.text.completed", {
          message_id: "message-1",
          content: "Use the ATAC-seq guidance as a source [1](source:1).",
        }),
      ],
    })

    fireEvent.click(screen.getByRole("button", { name: "Open 1 sources" }))

    expect(screen.getByRole("dialog", { name: "Sources" })).toBeInTheDocument()
    expect(screen.getByText("ATAC-seq peak calling review")).toBeInTheDocument()
  })

  it("does not make unsafe source URLs navigable in the sources drawer", () => {
    renderTranscript({
      events: [
        event("event-text", 1, "assistant.text.completed", {
          message_id: "message-1",
          content: "This source should not become a link [1](source:unsafe-source).",
          sources: [
            {
              id: "unsafe-source",
              title: "Unsafe source",
              url: "javascript:alert(1)",
              domain: "javascript:alert(1)",
              snippet: "A non-web URL echoed by a source provider.",
              sourceType: "web",
              query: "unsafe source",
              resultCount: 1,
            },
          ],
        }),
      ],
    })

    fireEvent.click(screen.getByRole("button", { name: "Open 1 sources" }))

    expect(screen.getByText("Unsafe source")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Unsafe source/ })).not.toBeInTheDocument()
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
  })

  it("does not make unsafe activity-row source URLs navigable", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input_preview: "unsafe echoed source",
          result: {
            results: [
              {
                title: "Unsafe search result",
                url: "javascript:alert(1)",
                snippet: "A non-web URL echoed by a source provider.",
              },
            ],
          },
        }),
      ],
    })

    fireEvent.click(screen.getByRole("button", { name: /Found 1 sources/ }))
    fireEvent.click(screen.getByRole("button", { name: /Show details/ }))

    expect(screen.getByText("Unsafe search result")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /Unsafe search result/ })).not.toBeInTheDocument()
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
  })

  it("keeps duplicate URL citation aliases resolvable after source dedupe", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input: { query: "duplicate source citations" },
          result: {
            query: "duplicate source citations",
            results: [
              {
                title: "Primary PubMed result",
                url: "https://pubmed.ncbi.nlm.nih.gov/12345/",
                snippet: "The first result snippet.",
              },
              {
                title: "Duplicate PubMed result",
                url: "https://pubmed.ncbi.nlm.nih.gov/12345/#abstract",
                snippet: "The second result snippet.",
              },
            ],
          },
        }),
        event("event-text", 2, "assistant.text.completed", {
          message_id: "message-1",
          content:
            "Both result aliases should stay clickable [1](source:1) and [2](source:2).",
        }),
      ],
    })

    expect(
      screen.getByRole("button", { name: /Source 1: Duplicate PubMed result/ }),
    ).toBeInTheDocument()
    const secondCitation = screen.getByRole("button", {
      name: /Source 2: Duplicate PubMed result/,
    })
    expect(secondCitation).toBeInTheDocument()

    fireEvent.focus(secondCitation)
    expect(screen.getByText("Source preview")).toBeInTheDocument()
    fireEvent.keyDown(secondCitation, { key: "Escape" })
    expect(screen.queryByText("Source preview")).not.toBeInTheDocument()
  })

  it("reports empty search results without inventing a source count", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input: { query: "unlikely empty bioinformatics query" },
          result: {
            query: "unlikely empty bioinformatics query",
            results: [],
          },
        }),
      ],
    })

    expect(screen.getByText("Found 0 sources")).toBeInTheDocument()
  })

  it("keeps running searches in a searching state before results arrive", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.started", {
          action_id: "action-search",
          name: "web.search",
          input: { query: "long running literature search" },
        }),
      ],
    })

    expect(screen.getByText("Searching sources...")).toBeInTheDocument()
    expect(screen.queryByText("Found 0 sources")).not.toBeInTheDocument()
  })

  it("shows provider search errors as failed activity with zero sources", () => {
    renderTranscript({
      events: [
        event("event-search", 1, "action.completed", {
          action_id: "action-search",
          name: "web.search",
          input: { query: "PubMed transient outage" },
          result: {
            query: "PubMed transient outage",
            results: [],
            error: "Search provider unavailable",
          },
        }),
      ],
    })

    expect(screen.getByText("Found 0 sources")).toBeInTheDocument()
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole("button", { name: /Found 0 sources/ }))
    fireEvent.click(screen.getByRole("button", { name: /Show details/ }))

    expect(screen.getByText("Error")).toBeInTheDocument()
    expect(screen.getByText("Search provider unavailable")).toBeInTheDocument()
  })
})
