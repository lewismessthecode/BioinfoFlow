import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTranscript } from "@/components/bioinfoflow/agent-runtime/agent-transcript"
import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"
import type {
  AgentRuntimeEvent,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
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
      "ask.customLabel": "Custom answer",
      "ask.customPlaceholder": "Tell Bioinfoflow what to use",
      "ask.recommended": "Recommended",
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
  onDecision,
}: {
  turn?: AgentRuntimeTurn
  events?: AgentRuntimeEvent[]
  onDecision?: Parameters<typeof AgentTranscript>[0]["onDecision"]
} = {}) {
  return render(
    <AgentTranscript
      timeline={buildAgentRuntimeTimeline([turn], events)}
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

    expect(screen.getByText("Read data")).toBeInTheDocument()
    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.queryByText("glob")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Read data/ }))

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

    expect(screen.getByText("Read data")).toBeInTheDocument()
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

    expect(screen.getByText("Read data")).toBeInTheDocument()
    expect(screen.getByText("Read 2 sources")).toBeInTheDocument()
    expect(screen.getByText("Manage workflows")).toBeInTheDocument()
    expect(screen.getByText("Managed 1 workflows")).toBeInTheDocument()
    expect(screen.getByText("Run commands")).toBeInTheDocument()
    expect(screen.getByText("Ran 1 commands")).toBeInTheDocument()
    expect(screen.getByText("Verify results")).toBeInTheDocument()
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

    expect(screen.getByText("Verify results")).toBeInTheDocument()
    expect(screen.getByText("Create or edit files")).toBeInTheDocument()
    expect(screen.queryByText("Run commands")).not.toBeInTheDocument()
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
    expect(screen.getByText("Read data")).toBeInTheDocument()
    expect(screen.getByText("Read 3 sources")).toBeInTheDocument()
    expect(screen.getByText("Run commands")).toBeInTheDocument()
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

    expect(screen.getByText("Submit run")).toBeInTheDocument()
    expect(screen.getByText("Failed")).toBeInTheDocument()
    expect(
      screen.queryByText("Image quay.io/example/missing:tag was not found"),
    ).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Submit run/ }))

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

    expect(screen.getByTestId("inline-ask-user-card")).toBeInTheDocument()
    expect(screen.getByText("Recommended")).toBeInTheDocument()
    fireEvent.change(screen.getByPlaceholderText("Tell Bioinfoflow what to use"), {
      target: { value: "T2T-CHM13" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }))

    expect(onDecision).toHaveBeenCalledWith("action-ask", "answer", {
      answer: { Genome: "T2T-CHM13" },
    })
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

    expect(screen.getByText("Read data")).toBeInTheDocument()
    expect(screen.queryByTestId("agent-tool-activity-row")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Read data/ }))

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
    expect(screen.getByText("Read data")).toBeInTheDocument()
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

    expect(screen.getByText("Searched web")).toBeInTheDocument()
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

    expect(screen.getByText("Searched web")).toBeInTheDocument()
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

    expect(screen.getByText("Searched web")).toBeInTheDocument()
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
    expect(screen.getByText("Failed")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Searched web/ }))
    fireEvent.click(screen.getByRole("button", { name: /Show details/ }))

    expect(screen.getByText("Error")).toBeInTheDocument()
    expect(screen.getByText("Search provider unavailable")).toBeInTheDocument()
  })
})
