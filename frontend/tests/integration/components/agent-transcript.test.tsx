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

const markdownRenderSpy = vi.hoisted(() => vi.fn())

vi.mock("@/components/bioinfoflow/markdown-renderer", () => ({
  MarkdownRenderer: ({ content }: { content: string }) => {
    markdownRenderSpy(content)
    return <div>{content}</div>
  },
}))

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentTranscript.title": "Conversation",
        "agentTranscript.copy": "Copy message",
        "agentTranscript.copied": "Copied",
        "agentTranscript.copy_failed": "Could not copy. Select the message and copy it manually.",
        "agentTranscript.retry": "Retry response",
        "agentTranscript.edit": "Edit message",
        "agentTranscript.timestamp": `Sent ${values?.time ?? ""}`,
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
        "agentActivity.details.copy": `Copy ${values?.label ?? "detail"}`,
        "agentActivity.details.copied": `Copied ${values?.label ?? "detail"}`,
        "agentActivity.details.copy_failed": "Could not copy detail",
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
        "agentThinking.title": "Thinking",
        "agentThinking.running": "Thinking…",
        "agentThinking.show": "Show thinking",
        "agentThinking.hide": "Hide thinking",
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
    markdownRenderSpy.mockClear()
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
  })

  it("degrades reasoning, tool, approval, and artifact cards independently", () => {
    const restrictedEntries: HistoryEntry[] = [
      ...entries,
      {
        ...entries[1],
        id: "restricted-parts",
        sequence: 4,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            { id: "visible-text", type: "text", text: "Visible response" },
            {
              id: "hidden-reasoning",
              type: "reasoning_summary",
              text: "Hidden reasoning",
            },
            {
              id: "hidden-tool",
              type: "tool_call",
              call_id: "call-hidden",
              group_id: "group-hidden",
              execution_mode: "serial",
              name: "bash",
              display_name: "Hidden tool",
              category: "command",
              summary: "Run a hidden tool",
              arguments: {},
            },
            {
              id: "hidden-artifact",
              type: "artifact_ref",
              artifact_id: "artifact-hidden",
              title: "hidden-report.html",
              media_type: "text/html",
            },
          ],
        },
      },
    ]

    renderWithProviders(
      <AgentTranscript
        entries={restrictedEntries}
        runs={[completedRun, pendingRun.run]}
        activeRun={pendingRun}
        capabilities={{
          reasoning: false,
          toolActivity: false,
          approvals: false,
          artifacts: false,
          starterPrompts: true,
          multiTargetExecution: true,
          retry: true,
          editAndResend: true,
        }}
      />,
    )

    expect(screen.getByText("Visible response")).toBeInTheDocument()
    expect(screen.queryByText("Hidden reasoning")).not.toBeInTheDocument()
    expect(screen.queryByText("Hidden tool")).not.toBeInTheDocument()
    expect(screen.queryByText("hidden-report.html")).not.toBeInTheDocument()
    expect(screen.queryByTestId("agent-interaction-card")).not.toBeInTheDocument()
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

  it("exposes semantic timestamps and routes Retry/Edit to their canonical messages", async () => {
    const user = userEvent.setup()
    const onRetryMessage = vi.fn().mockResolvedValue(undefined)
    const onEditMessage = vi.fn()

    renderWithProviders(
      <AgentTranscript
        entries={entries.slice(0, 2)}
        runs={[completedRun]}
        activeRun={null}
        onRetryMessage={onRetryMessage}
        onEditMessage={onEditMessage}
      />,
    )

    const timestamps = screen.getAllByText(/Sent/)
    expect(timestamps).toHaveLength(2)
    expect(timestamps[0]).toHaveAttribute("datetime", entries[0].created_at)
    expect(timestamps[1]).toHaveAttribute("datetime", entries[1].created_at)

    await user.click(screen.getByRole("button", { name: "Edit message" }))
    expect(onEditMessage).toHaveBeenCalledWith(entries[0])

    await user.click(screen.getByRole("button", { name: "Retry response" }))
    expect(onRetryMessage).toHaveBeenCalledWith(entries[1])
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

  it("preserves a tool disclosure when a live tool becomes durable", async () => {
    const user = userEvent.setup()
    const liveTool = {
      call_id: "call-stable",
      group_id: "group-stable",
      execution_mode: "serial" as const,
      name: "bash",
      display_name: "Bash",
      category: "command" as const,
      summary: "Run workflow",
      arguments: {},
      status: "running" as const,
      revision: 1,
      started_at: "2026-08-15T08:00:01.000Z",
      completed_at: null,
      input_summary: null,
      output_summary: null,
      error: null,
      public_details: [
        {
          id: "command",
          kind: "command" as const,
          label: "Command",
          value: "nextflow run main.nf",
          format: "code" as const,
          copyable: true,
          truncated: false,
          redacted: false,
        },
      ],
    }
    const activeRun: ActiveRunView = {
      run: { ...pendingRun.run, id: "run-stable", status: "running", phase: "tools" },
      assistant_draft: null,
      tool_progress: [liveTool],
      pending_interaction: null,
    }
    const view = renderWithProviders(
      <AgentTranscript entries={[]} runs={[activeRun.run]} activeRun={activeRun} />,
    )

    await user.click(screen.getByRole("button", { name: /Show details/i }))
    expect(screen.getByText("nextflow run main.nf")).toBeInTheDocument()

    const durableEntry: HistoryEntry = {
      id: "durable-tool",
      session_id: "session-1",
      run_id: "run-stable",
      sequence: 1,
      schema_version: 2,
      created_at: "2026-08-15T08:00:02.000Z",
      type: "message",
      payload: {
        role: "assistant",
        parts: [
          {
            id: "call-part-stable",
            type: "tool_call",
            call_id: liveTool.call_id,
            group_id: liveTool.group_id,
            execution_mode: liveTool.execution_mode,
            name: liveTool.name,
            display_name: liveTool.display_name,
            category: liveTool.category,
            summary: liveTool.summary,
            arguments: {},
            public_details: liveTool.public_details,
          },
        ],
      },
    }
    view.rerender(
      <AgentTranscript
        entries={[durableEntry]}
        runs={[activeRun.run]}
        activeRun={{ ...activeRun, tool_progress: [{ ...liveTool, revision: 2 }] }}
      />,
    )

    expect(screen.getAllByTestId("agent-tool-card")).toHaveLength(1)
    expect(screen.getByText("nextflow run main.nf")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Hide details/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    )
  })

  it("preserves thinking disclosure when a stable reasoning part becomes durable", async () => {
    const user = userEvent.setup()
    const activeRun: ActiveRunView = {
      run: { ...pendingRun.run, id: "run-thinking", status: "running", phase: "model" },
      assistant_draft: {
        id: "draft-thinking",
        run_id: "run-thinking",
        parts: [
          {
            id: "reasoning-stable",
            type: "reasoning_summary",
            text: "Inspect first.\nValidate second.",
            end_offset: 31,
          },
        ],
      },
      tool_progress: [],
      pending_interaction: null,
    }
    const view = renderWithProviders(
      <AgentTranscript entries={[]} runs={[activeRun.run]} activeRun={activeRun} />,
    )

    await user.click(screen.getByRole("button", { name: /Show thinking/i }))
    expect(screen.getByText(/Validate second/)).toBeInTheDocument()

    const durableEntry: HistoryEntry = {
      id: "durable-thinking",
      session_id: "session-1",
      run_id: "run-thinking",
      sequence: 1,
      schema_version: 2,
      created_at: "2026-08-15T08:00:02.000Z",
      type: "message",
      payload: {
        role: "assistant",
        parts: [
          {
            id: "reasoning-stable",
            type: "reasoning_summary",
            text: "Inspect first.\nValidate second.",
          },
        ],
      },
    }
    view.rerender(
      <AgentTranscript entries={[durableEntry]} runs={[activeRun.run]} activeRun={null} />,
    )

    expect(screen.getByText(/Validate second/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Hide thinking/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    )
  })

  it("does not rerender unrelated historical markdown for a live tool revision", () => {
    const toolEntry: HistoryEntry = {
      id: "tool-entry",
      session_id: "session-1",
      run_id: "run-tools",
      sequence: 2,
      schema_version: 2,
      created_at: "2026-08-15T08:00:01.000Z",
      type: "message",
      payload: {
        role: "assistant",
        parts: [
          {
            id: "call-part",
            type: "tool_call",
            call_id: "call-live",
            group_id: "group-live",
            execution_mode: "serial",
            name: "read",
            display_name: "Read",
            category: "read",
            summary: "Read workflow.nf",
            arguments: {},
          },
        ],
      },
    }
    const activeRun: ActiveRunView = {
      run: { ...pendingRun.run, id: "run-tools", status: "running", phase: "tools" },
      assistant_draft: null,
      tool_progress: [
        {
          call_id: "call-live",
          group_id: "group-live",
          execution_mode: "serial",
          name: "read",
          display_name: "Read",
          category: "read",
          summary: "Read workflow.nf",
          arguments: {},
          status: "running",
          revision: 1,
          started_at: null,
          completed_at: null,
          input_summary: null,
          output_summary: null,
          error: null,
        },
      ],
      pending_interaction: null,
    }
    const stableEntries = [entries[0], toolEntry]
    const view = renderWithProviders(
      <AgentTranscript entries={stableEntries} runs={[activeRun.run]} activeRun={activeRun} />,
    )
    markdownRenderSpy.mockClear()

    view.rerender(
      <AgentTranscript
        entries={stableEntries}
        runs={[activeRun.run]}
        activeRun={{
          ...activeRun,
          tool_progress: [{ ...activeRun.tool_progress[0], revision: 2 }],
        }}
      />,
    )

    expect(markdownRenderSpy).not.toHaveBeenCalledWith("Inspect this workflow.")
  })

  it("does not remeasure the history anchor for an active-only revision", () => {
    const activeRun: ActiveRunView = {
      run: { ...pendingRun.run, id: "run-stream", status: "running", phase: "model" },
      assistant_draft: {
        id: "draft-stream",
        run_id: "run-stream",
        parts: [
          {
            id: "draft-stream-text",
            type: "text",
            text: "Working",
            end_offset: 7,
          },
        ],
      },
      tool_progress: [],
      pending_interaction: null,
    }
    const stableEntries = entries.slice(0, 2)
    const stableRuns = [activeRun.run]
    const view = renderWithProviders(
      <AgentTranscript
        entries={stableEntries}
        runs={stableRuns}
        activeRun={activeRun}
      />,
    )
    const transcript = screen.getByTestId("agent-transcript")
    Object.defineProperties(transcript, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, writable: true, value: 100 },
    })
    const rectSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue(domRect(0, 100))

    fireEvent.scroll(transcript)
    rectSpy.mockClear()
    view.rerender(
      <AgentTranscript
        entries={stableEntries}
        runs={stableRuns}
        activeRun={{
          ...activeRun,
          assistant_draft: {
            ...activeRun.assistant_draft!,
            parts: [
              {
                ...activeRun.assistant_draft!.parts[0],
                text: "Working on the next step",
                end_offset: 24,
              },
            ],
          },
        }}
      />,
    )

    expect(rectSpy).not.toHaveBeenCalled()
    rectSpy.mockRestore()
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
