import { fireEvent, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentTranscript } from "@/components/bioinfoflow/agent/agent-transcript"
import type {
  ActiveRunView,
  HistoryEntry,
  InteractionResponse,
  RunView,
} from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentTranscript.title": "Conversation",
        "agentTranscript.copy": "Copy message",
        "agentTranscript.copied": "Copied",
        "agentTranscript.copy_failed": "Could not copy. Select the message and copy it manually.",
        "agentTranscript.scroll_to_bottom": "Jump to latest",
        "agentTranscript.run_ended": `Ended ${values?.time ?? ""}`,
        "agentTranscript.run_duration": `${values?.duration ?? ""}`,
        "agentRun.title": "Agent run in progress",
        "agentRun.status.running": "Running",
        "agentRun.status.waiting_user": "Waiting for input",
        "agentRun.status.completed": "Completed",
        "agentRun.status.failed": "Failed",
        "agentRun.status.cancelled": "Cancelled",
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
        "agentHistory.reasoning.title": "Thinking summary",
        "agentHistory.notice.title": "Agent notice",
        "agentInteraction.status.pending": "Waiting for response",
        "agentInteraction.approval.title": "Approval requested",
        "agentInteraction.approval.approve": "Approve",
        "agentInteraction.approval.reject": "Reject",
        "agentInteraction.approval.input": "Command preview",
        "agentInteraction.approval.effects": "Effects",
        "agentInteraction.approval.reasons": "Reasons",
        "agentInteraction.approval.resources": "Affected resources",
        "agentInteraction.submitting": "Submitting…",
        "agentInteraction.submit_failed": "Could not submit the response.",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const completedRun: RunView = {
  id: "run-1",
  session_id: "session-1",
  status: "completed",
  phase: null,
  revision: 5,
  started_at: "2026-08-15T08:00:00.000Z",
  completed_at: "2026-08-15T08:00:02.500Z",
  termination_reason: "completed",
  error: null,
  created_at: "2026-08-15T08:00:00.000Z",
  updated_at: "2026-08-15T08:00:02.500Z",
}

const pendingRun: ActiveRunView = {
  run: {
    ...completedRun,
    id: "run-2",
    status: "waiting_user",
    phase: "interaction",
    revision: 3,
    completed_at: null,
    termination_reason: null,
  },
  assistant_draft: {
    id: "draft-2",
    run_id: "run-2",
    parts: [
      {
        id: "draft-text-2",
        type: "text",
        text: "I need approval before continuing.",
        end_offset: 34,
      },
    ],
  },
  tool_progress: [],
  pending_interaction: {
    interaction_id: "interaction-1",
    run_id: "run-2",
    revision: 1,
    request: {
      type: "approval",
      call_id: "call-approval",
      tool_name: "bash",
      summary: "Install the workflow dependency",
      input_preview: "uv sync",
      allowed_responses: ["approve", "reject"],
      risk: {
        level: "medium",
        effects: ["Writes dependency files"],
        reasons: ["The command changes the workspace"],
        affected_resources: ["uv.lock"],
      },
    },
  },
}

const entries: HistoryEntry[] = [
  {
    id: "message-user",
    session_id: "session-1",
    run_id: "run-1",
    sequence: 1,
    schema_version: 2,
    created_at: "2026-08-15T08:00:00.000Z",
    type: "message",
    payload: {
      role: "user",
      parts: [{ id: "user-text", type: "text", text: "Inspect this workflow." }],
    },
  },
  {
    id: "message-assistant",
    session_id: "session-1",
    run_id: "run-1",
    sequence: 2,
    schema_version: 2,
    created_at: "2026-08-15T08:00:02.500Z",
    type: "message",
    payload: {
      role: "assistant",
      parts: [{ id: "assistant-text", type: "text", text: "The workflow is valid." }],
    },
  },
  {
    id: "interaction-request",
    session_id: "session-1",
    run_id: "run-2",
    sequence: 3,
    schema_version: 2,
    created_at: "2026-08-15T08:00:03.000Z",
    type: "interaction_request",
    payload: {
      interaction_id: "interaction-1",
      request: pendingRun.pending_interaction!.request,
    },
  },
]

describe("AgentTranscript", () => {
  beforeEach(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it("combines durable history, active work, run timing, copy, and one actionable interaction", async () => {
    const user = userEvent.setup()
    const writeText = vi
      .spyOn(navigator.clipboard, "writeText")
      .mockResolvedValue(undefined)
    const onRespond = vi.fn<
      (interactionId: string, response: InteractionResponse) => Promise<void>
    >().mockResolvedValue(undefined)

    renderWithProviders(
      <AgentTranscript
        entries={entries}
        runs={[completedRun, pendingRun.run]}
        activeRun={pendingRun}
        onRespond={onRespond}
      />,
    )

    expect(screen.getByRole("region", { name: "Conversation" })).toHaveTextContent(
      "The workflow is valid.",
    )
    expect(screen.getByTestId("agent-transcript-content")).toHaveClass(
      "max-w-[46rem]",
    )
    expect(screen.getByText("I need approval before continuing.")).toBeInTheDocument()
    expect(screen.getAllByTestId("agent-interaction-card")).toHaveLength(1)
    expect(screen.getByTestId("agent-run-outcome")).toHaveTextContent(
      "Completed",
    )
    expect(screen.getByText(/Ended/)).toHaveAttribute(
      "datetime",
      completedRun.completed_at,
    )
    expect(screen.getByText("2.5 s")).toBeInTheDocument()

    const copyButtons = screen.getAllByRole("button", { name: "Copy message" })
    expect(copyButtons).toHaveLength(2)
    await user.click(copyButtons[1])
    expect(writeText).toHaveBeenCalledWith("The workflow is valid.")
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Approve" }))
    expect(onRespond).toHaveBeenCalledWith("interaction-1", {
      type: "approval",
      approved: true,
    })
  })

  it("renders a durable tool call once while applying its live progress in place", () => {
    const toolEntries: HistoryEntry[] = [
      {
        id: "assistant-tool-call",
        session_id: "session-1",
        run_id: "run-tools",
        sequence: 1,
        schema_version: 2,
        created_at: "2026-08-15T08:00:00.000Z",
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "call-part-1",
              type: "tool_call",
              call_id: "call-1",
              group_id: "group-1",
              execution_mode: "serial",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read workflow.nf",
              arguments: { path: "workflow.nf" },
            },
          ],
        },
      },
    ]
    const activeRun: ActiveRunView = {
      run: {
        ...pendingRun.run,
        id: "run-tools",
        status: "running",
        phase: "tools",
      },
      assistant_draft: null,
      tool_progress: [
        {
          call_id: "call-1",
          group_id: "group-1",
          execution_mode: "serial",
          name: "read",
          display_name: "Read",
          category: "read",
          summary: "Read workflow.nf",
          arguments: { path: "workflow.nf" },
          status: "running",
          revision: 2,
          started_at: "2026-08-15T08:00:01.000Z",
          completed_at: null,
          input_summary: "workflow.nf",
          output_summary: null,
          error: null,
        },
      ],
      pending_interaction: null,
    }

    renderWithProviders(
      <AgentTranscript
        entries={toolEntries}
        runs={[activeRun.run]}
        activeRun={activeRun}
      />,
    )

    const cards = screen.getAllByTestId("agent-tool-card")
    expect(cards).toHaveLength(1)
    expect(cards[0]).toHaveTextContent("Read workflow.nf")
    expect(cards[0]).toHaveTextContent("Running")
  })

  it("pauses bottom-follow while reading history and resumes it on request", async () => {
    const user = userEvent.setup()
    const view = renderWithProviders(
      <AgentTranscript
        entries={entries.slice(0, 2)}
        runs={[completedRun]}
        activeRun={null}
      />,
    )
    const transcript = screen.getByTestId("agent-transcript")
    const scrollTo = vi.fn()
    Object.defineProperties(transcript, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, writable: true, value: 100 },
      scrollTo: { configurable: true, value: scrollTo },
    })

    fireEvent.scroll(transcript)
    view.rerender(
      <AgentTranscript
        entries={[
          ...entries.slice(0, 2),
          {
            id: "notice-new",
            session_id: "session-1",
            run_id: null,
            sequence: 3,
            schema_version: 2,
            created_at: "2026-08-15T08:00:03.000Z",
            type: "notice",
            payload: {
              code: "new-content",
              message: "A new update arrived.",
              details: null,
            },
          },
        ]}
        runs={[completedRun]}
        activeRun={null}
      />,
    )

    const jumpButton = await screen.findByRole("button", {
      name: "Jump to latest",
    })
    expect(jumpButton).toHaveTextContent("Jump to latest")
    expect(scrollTo).not.toHaveBeenCalled()

    await user.click(jumpButton)
    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: "smooth" })
    expect(
      screen.queryByRole("button", { name: "Jump to latest" }),
    ).not.toBeInTheDocument()

    scrollTo.mockClear()
    transcript.scrollTop = 600
    fireEvent.scroll(transcript)
    view.rerender(
      <AgentTranscript
        entries={[
          ...entries.slice(0, 2),
          {
            id: "notice-newer",
            session_id: "session-1",
            run_id: null,
            sequence: 4,
            schema_version: 2,
            created_at: "2026-08-15T08:00:04.000Z",
            type: "notice",
            payload: {
              code: "newer-content",
              message: "Another update arrived.",
              details: null,
            },
          },
        ]}
        runs={[completedRun]}
        activeRun={null}
      />,
    )

    await waitFor(() =>
      expect(scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "auto",
      }),
    )
    expect(
      screen.queryByRole("button", { name: "Jump to latest" }),
    ).not.toBeInTheDocument()
  })

  it("treats a historical Run revision becoming failed as new transcript content", async () => {
    const runningRun: RunView = {
      ...completedRun,
      status: "running",
      phase: "model",
      revision: 1,
      completed_at: null,
      termination_reason: null,
    }
    const failedRun: RunView = {
      ...completedRun,
      status: "failed",
      revision: 2,
      termination_reason: "agent_failed",
      error: {
        code: "agent_failed",
        message: "The Agent run failed.",
      },
    }
    const view = renderWithProviders(
      <AgentTranscript
        entries={entries.slice(0, 1)}
        runs={[runningRun]}
        activeRun={null}
      />,
    )
    const transcript = screen.getByTestId("agent-transcript")
    Object.defineProperties(transcript, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    })
    fireEvent.scroll(transcript)

    view.rerender(
      <AgentTranscript
        entries={entries.slice(0, 1)}
        runs={[failedRun]}
        activeRun={null}
      />,
    )

    expect(screen.getByTestId("agent-run-outcome")).toHaveTextContent("Failed")
    expect(
      await screen.findByRole("button", { name: "Jump to latest" }),
    ).toBeInTheDocument()
  })

  it("keeps the visible history anchor in place when authoritative content is replaced", () => {
    const view = renderWithProviders(
      <AgentTranscript
        entries={entries.slice(0, 2)}
        runs={[completedRun]}
        activeRun={null}
      />,
    )
    const transcript = screen.getByTestId("agent-transcript")
    let assistantTop = 80
    Object.defineProperties(transcript, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    })
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(function () {
        if (this === transcript) return domRect(0, 400)
        const anchor = this.getAttribute("data-agent-read-anchor")
        if (anchor === "entry:message-user") return domRect(-180, -80)
        if (anchor === "entry:message-assistant") {
          return domRect(assistantTop, assistantTop + 120)
        }
        return domRect(0, 0)
      })

    fireEvent.scroll(transcript)
    assistantTop = 180
    view.rerender(
      <AgentTranscript
        entries={[
          {
            id: "notice-before",
            session_id: "session-1",
            run_id: null,
            sequence: 0,
            schema_version: 2,
            created_at: "2026-08-15T07:59:59.000Z",
            type: "notice",
            payload: {
              code: "recovered-history",
              message: "Recovered earlier history.",
              details: null,
            },
          },
          ...entries.slice(0, 2),
        ]}
        runs={[completedRun]}
        activeRun={null}
      />,
    )

    expect(transcript.scrollTop).toBe(200)
    rectSpy.mockRestore()
  })

  it("announces a recoverable copy failure without showing a success toast", async () => {
    const user = userEvent.setup()
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(
      new Error("Clipboard permission denied"),
    )

    renderWithProviders(
      <AgentTranscript
        entries={entries.slice(0, 1)}
        runs={[completedRun]}
        activeRun={null}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Copy message" }))

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Could not copy. Select the message and copy it manually.",
    )
    expect(screen.queryByText("Copied")).not.toBeInTheDocument()
  })

  it("uses an instant jump when reduced motion is requested", async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: true,
        media: "(prefers-reduced-motion: reduce)",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }),
    )
    const view = renderWithProviders(
      <AgentTranscript
        entries={entries.slice(0, 1)}
        runs={[completedRun]}
        activeRun={null}
      />,
    )
    const transcript = screen.getByTestId("agent-transcript")
    const scrollTo = vi.fn()
    Object.defineProperties(transcript, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, writable: true, value: 100 },
      scrollTo: { configurable: true, value: scrollTo },
    })

    fireEvent.scroll(transcript)
    view.rerender(
      <AgentTranscript
        entries={entries.slice(0, 2)}
        runs={[completedRun]}
        activeRun={null}
      />,
    )
    await user.click(
      await screen.findByRole("button", { name: "Jump to latest" }),
    )

    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: "auto" })
    vi.unstubAllGlobals()
  })
})

function domRect(top: number, bottom: number): DOMRect {
  return {
    x: 0,
    y: top,
    width: 600,
    height: bottom - top,
    top,
    right: 600,
    bottom,
    left: 0,
    toJSON: () => ({}),
  }
}
