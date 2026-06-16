import type * as React from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentWorkbench } from "@/components/bioinfoflow/agent-runtime/agent-workbench"
import type {
  AgentRuntimeEvent,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"

const useAgentRuntimeMock = vi.fn()
const useLlmSettingsMock = vi.fn()
const setNavbarActionsMock = vi.fn()

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      welcomeTitle: "What should Bioinfoflow help you do today?",
      composerPlaceholder: "Message Bioinfoflow...",
      attach: "Attach or add context",
      send: "Send message",
      stop: "Stop response",
      pendingResponse: "Working on it...",
      thinking: "Thinking",
      showThinking: "Show thinking",
      hideThinking: "Hide thinking",
      toolCalls: "Tool calls",
      "activity.groups.read": "Read project structure",
      "activity.summary.read": "Read 1 source",
      approve: "Approve",
      reject: "Reject",
      "approval.state.approved": "Approved, resuming",
      "approval.jumpToDecision": "Jump to decision",
      "turnStatus.running": "Working",
      "turnStatus.completed": "Done",
      "sidecar.title": "Run",
      "sidecar.close": "Close run panel",
      "sidecar.collapse": "Collapse run panel",
      "sidecar.expand": "Open run panel",
      "sidecar.files": "Files",
      "sidecar.runs": "Runs",
      "sidecar.tools": "Tools",
      "sidecar.artifacts": "Artifacts",
      "sidecar.active": "Active",
      "sidecar.progress": "Progress",
      "sidecar.currentThinking": "Current thinking",
      "sidecar.currentToolCalls": "Current tool calls",
      "sidecar.needsDecision": "Needs your decision",
      "sidecar.noActivity": "No activity yet",
      "attachMenu.attachFiles": "Attach files",
      "attachMenu.browseProjectFiles": "Browse project files",
      "attachMenu.referenceRun": "Reference a run",
      "attachMenu.runPreflight": "Run preflight",
      "attachMenu.diagnoseRun": "Diagnose run",
      "attachMenu.comingSoon": "Coming soon",
      auto: "Auto",
      configure: "Configure providers",
      noProviders: "No model available",
      searchModels: "Search models...",
    }
    return labels[key] ?? key
  },
}))

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/hooks/use-agent-runtime", () => ({
  useAgentRuntime: (...args: unknown[]) => useAgentRuntimeMock(...args),
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: () => useLlmSettingsMock(),
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useOptionalWorkspaceShell: () => ({
    setNavbarActions: setNavbarActionsMock,
  }),
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => (
    <span aria-hidden="true" data-provider={provider} />
  ),
}))

const baseTurn: AgentRuntimeTurn = {
  id: "turn-1",
  session_id: "session-1",
  project_id: null,
  workspace_id: "workspace-1",
  user_id: "user-1",
  input_text: "Analyze these FASTQ files.",
  status: "completed",
  model_selection: null,
  final_text: "The files look ready.",
  token_usage: null,
  termination_reason: null,
  loop_state: null,
  iteration_count: 1,
  budget_snapshot: null,
  created_at: "2026-06-09T00:00:00Z",
  updated_at: "2026-06-09T00:00:00Z",
}

const waitingDecisionEvent: AgentRuntimeEvent = {
  id: "event-1",
  session_id: "session-1",
  turn_id: "turn-1",
  seq: 1,
  type: "action.waiting_decision",
  payload: { action_id: "action-1", name: "files__write" },
  visibility: "user",
  schema_version: 1,
  created_at: "2026-06-09T00:00:00Z",
  updated_at: "2026-06-09T00:00:00Z",
}

function setupRuntime({
  turns = [],
  events = [],
  status = "idle",
}: {
  turns?: AgentRuntimeTurn[]
  events?: AgentRuntimeEvent[]
  status?: "idle" | "loading" | "running" | "error"
} = {}) {
  useAgentRuntimeMock.mockReturnValue({
    state: {
      session: null,
      turns,
      events,
      timeline: buildAgentRuntimeTimeline(turns, events),
      status,
      error: null,
    },
    setActiveSessionId: vi.fn(),
    send: vi.fn(),
    interrupt: vi.fn(),
    decideAction: vi.fn(),
  })
}

describe("AgentWorkbench", () => {
  beforeEach(() => {
    useAgentRuntimeMock.mockReset()
    useLlmSettingsMock.mockReset()
    setNavbarActionsMock.mockReset()
    useLlmSettingsMock.mockReturnValue({
      models: [],
      selectedModel: null,
      isLoading: false,
      setSelectedModel: vi.fn(),
    })
    setupRuntime()
  })

  it("renders the new chat welcome with a centered composer", () => {
    render(<AgentWorkbench />)

    expect(
      screen.getByText("What should Bioinfoflow help you do today?"),
    ).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "center",
    )
    expect(screen.queryByText("Agent Harness")).not.toBeInTheDocument()
    expect(screen.queryByText("Start from the runtime")).not.toBeInTheDocument()
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
  })

  it("registers the runtime sidecar toggle with the navbar action group", () => {
    render(<AgentWorkbench />)

    expect(setNavbarActionsMock).toHaveBeenCalled()
    const lastCall = setNavbarActionsMock.mock.calls.at(-1)
    expect(lastCall?.[0]).toBeTruthy()
    expect(
      screen.queryByRole("button", { name: "Open run panel" }),
    ).not.toBeInTheDocument()
  })

  it("moves the composer to the bottom after a turn exists", () => {
    setupRuntime({ turns: [baseTurn] })

    render(<AgentWorkbench />)

    expect(screen.getByText("Analyze these FASTQ files.")).toBeInTheDocument()
    expect(screen.getByText("The files look ready.")).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
  })

  it("keeps an active loading session in the conversation layout", () => {
    setupRuntime({ turns: [], status: "loading" })

    render(<AgentWorkbench activeSessionId="session-1" />)

    expect(
      screen.queryByText("What should Bioinfoflow help you do today?"),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
  })

  it("shows an optimistic pending response immediately after submitting the centered composer", () => {
    const send = vi.fn(() => new Promise(() => {}))
    useAgentRuntimeMock.mockReturnValue({
      state: {
        session: null,
        turns: [],
        events: [],
        timeline: [],
        status: "loading",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Plan RNA-seq QC" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
    expect(screen.getByText("Plan RNA-seq QC")).toBeInTheDocument()
    expect(screen.getByText("Working on it...")).toBeInTheDocument()
  })

  it("opens a placeholder attachment menu without sending a message", async () => {
    const send = vi.fn()
    useAgentRuntimeMock.mockReturnValue({
      state: {
        session: null,
        turns: [],
        events: [],
        timeline: [],
        status: "idle",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    })

    render(<AgentWorkbench />)

    fireEvent.pointerDown(
      screen.getByRole("button", { name: "Attach or add context" }),
    )

    expect(
      await screen.findByRole("menuitem", { name: "Attach files" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Browse project files" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Reference a run" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Run preflight" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Diagnose run" }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole("menuitem", { name: "Attach files" }))

    expect(send).not.toHaveBeenCalled()
  })

  it("renders the only approval controls inline and a jump prompt above the composer", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "waiting_approval", final_text: null }],
      events: [waitingDecisionEvent],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.getByTestId("composer-approval-popover")).toBeInTheDocument()
    expect(screen.getByTestId("composer-decision-jump")).toBeInTheDocument()
    expect(screen.getByTestId("inline-approval-card")).toBeInTheDocument()
    expect(screen.queryByTestId("pending-decisions")).not.toBeInTheDocument()
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    expect(screen.getAllByText("Needs your decision").length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument()
    expect(screen.getByText("Jump to decision")).toBeInTheDocument()
  })

  it("does not auto-open the panel merely because the agent is streaming", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        {
          ...waitingDecisionEvent,
          type: "assistant.text.delta",
          payload: { content: "thinking" },
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
  })

  it("renders thinking and tool-call activity in the transcript", async () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        {
          id: "event-thinking",
          session_id: "session-1",
          turn_id: "turn-1",
          seq: 1,
          type: "assistant.thinking.completed",
          payload: {
            message_id: "message-1",
            content: "Inspecting the project state.",
            index: 0,
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-09T00:00:00Z",
          updated_at: "2026-06-09T00:00:00Z",
        },
        {
          id: "event-tool",
          session_id: "session-1",
          turn_id: "turn-1",
          seq: 2,
          type: "assistant.tool_call.completed",
          payload: {
            message_id: "message-1",
            call_id: "call-1",
            name: "projects__list",
            arguments: { limit: 1 },
            status: "completed",
            index: 0,
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-09T00:00:00Z",
          updated_at: "2026-06-09T00:00:00Z",
        },
        {
          id: "event-text",
          session_id: "session-1",
          turn_id: "turn-1",
          seq: 3,
          type: "assistant.text.completed",
          payload: {
            message_id: "message-1",
            text: "Project scan complete.",
            content: "Project scan complete.",
            index: 0,
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-09T00:00:00Z",
          updated_at: "2026-06-09T00:00:00Z",
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(await screen.findByText("Thinking")).toBeInTheDocument()
    expect(screen.getByText("Project scan complete.")).toBeInTheDocument()
    expect(screen.getByText("Read project structure")).toBeInTheDocument()
  })

  it("keeps an approved approval visible until resume progress arrives", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        waitingDecisionEvent,
        {
          ...waitingDecisionEvent,
          id: "event-2",
          seq: 2,
          type: "action.decision_recorded",
          payload: { action_id: "action-1", decision: "approve" },
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.getByTestId("composer-approval-popover")).toBeInTheDocument()
    expect(screen.getAllByText("Approved, resuming").length).toBeGreaterThan(0)
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
  })

  it("clears the approved approval once resume progress arrives", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        waitingDecisionEvent,
        {
          ...waitingDecisionEvent,
          id: "event-2",
          seq: 2,
          type: "action.decision_recorded",
          payload: { action_id: "action-1", decision: "approve" },
        },
        {
          ...waitingDecisionEvent,
          id: "event-3",
          seq: 3,
          type: "assistant.text.delta",
          payload: { content: "Resumed." },
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.queryByTestId("composer-approval-popover")).not.toBeInTheDocument()
    expect(screen.getByText("Approved, resuming")).toBeInTheDocument()
  })
})
