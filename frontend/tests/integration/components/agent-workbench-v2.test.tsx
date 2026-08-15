import { act, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentWorkbench } from "@/components/bioinfoflow/agent/agent-workbench"
import type { SessionSnapshot } from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

const mocks = vi.hoisted(() => ({
  createSession: vi.fn(),
  dispatchCommand: vi.fn(),
  publishSummary: vi.fn(),
  replace: vi.fn(),
  push: vi.fn(),
  useSession: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
}))

vi.mock("@/lib/agent/client", () => ({
  createAgentSession: mocks.createSession,
  dispatchAgentCommand: mocks.dispatchCommand,
}))

vi.mock("@/lib/agent/session-preferences", () => ({
  publishAgentSessionSummary: mocks.publishSummary,
  sessionSummaryFromView: (session: Record<string, unknown>) => session,
}))

vi.mock("@/hooks/use-agent-session", () => ({
  useAgentSession: (...args: unknown[]) => mocks.useSession(...args),
}))

vi.mock("@/components/bioinfoflow/agent/agent-context-picker", () => ({
  AgentContextPicker: () => <button type="button">Add context</button>,
}))

vi.mock("@/components/bioinfoflow/agent/agent-transcript", () => ({
  AgentTranscript: ({ entries }: { entries: unknown[] }) => (
    <div data-testid="transcript">entries:{entries.length}</div>
  ),
}))

vi.mock("@/components/bioinfoflow/agent/agent-composer", () => ({
  AgentComposer: ({
    onSendMessage,
    onCancel,
  }: {
    onSendMessage: (parts: [{ type: "text"; text: string }]) => Promise<void>
    onCancel: () => Promise<void>
  }) => (
    <div>
      <button
        type="button"
        onClick={() => onSendMessage([{ type: "text", text: "Hello" }])}
      >
        Send message
      </button>
      <button type="button" onClick={() => onCancel()}>
        Stop run
      </button>
    </div>
  ),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

const timestamp = "2026-08-15T00:00:00Z"

function snapshot(): SessionSnapshot {
  return {
    session: {
      id: "session-1",
      user_id: "user-1",
      workspace_id: "workspace-1",
      project_id: "project-1",
      title: "Variant review",
      model: {
        provider: "openai",
        model: "gpt-5.6",
        display_name: "GPT-5.6",
        supports_vision: true,
        supports_reasoning: true,
        supports_tools: true,
      },
      permission_mode: "ask_dangerous",
      workspace_access: "read_write",
      status: "active",
      created_at: timestamp,
      updated_at: timestamp,
    },
    runs: [],
    entries: [],
    active_run: null,
    history_revision: 0,
  }
}

function sessionState(overrides: Record<string, unknown> = {}) {
  return {
    session: snapshot().session,
    runs: [],
    entries: [],
    activeRun: null,
    historyRevision: 0,
    connectionStatus: "connected",
    error: null,
    isLoading: false,
    sendMessage: vi.fn().mockResolvedValue(undefined),
    steer: vi.fn().mockResolvedValue(undefined),
    respond: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn().mockResolvedValue(undefined),
    updatePermissionMode: vi.fn().mockResolvedValue(undefined),
    retry: vi.fn(),
    ...overrides,
  }
}

describe("AgentWorkbench v2", () => {
  beforeEach(() => {
    mocks.createSession.mockReset()
    mocks.dispatchCommand.mockReset()
    mocks.publishSummary.mockReset()
    mocks.replace.mockReset()
    mocks.push.mockReset()
    mocks.useSession.mockReset()
    mocks.useSession.mockReturnValue(sessionState())
  })

  it("creates the draft session once, sends the public message command, and routes to it", async () => {
    const user = userEvent.setup()
    mocks.createSession.mockResolvedValue(snapshot())
    mocks.dispatchCommand.mockResolvedValue(snapshot())

    renderWithProviders(
      <AgentWorkbench
        sessionId={null}
        projectId="project-1"
        onActiveSessionIdChange={vi.fn()}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Send message" }))

    await waitFor(() => expect(mocks.createSession).toHaveBeenCalledTimes(1))
    expect(mocks.createSession).toHaveBeenCalledWith({
      projectId: "project-1",
      permissionMode: "ask_dangerous",
      workspaceAccess: "read_write",
    })
    expect(mocks.dispatchCommand).toHaveBeenCalledWith(
      "session-1",
      expect.objectContaining({
        type: "message",
        parts: [{ type: "text", text: "Hello" }],
      }),
    )
    expect(mocks.publishSummary).toHaveBeenCalled()
    expect(mocks.replace).toHaveBeenCalledWith("/agent/session-1")
  })

  it("renders the authoritative session and keeps stream interruptions visible but non-destructive", () => {
    mocks.useSession.mockReturnValue(
      sessionState({
        connectionStatus: "reconnecting",
        error: new Error("Agent event stream disconnected"),
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.getByText("Variant review")).toBeInTheDocument()
    expect(screen.getByText("GPT-5.6")).toBeInTheDocument()
    expect(screen.getByText("emptyTitle")).toBeInTheDocument()
    expect(screen.getAllByText("connection.reconnecting")).toHaveLength(2)
  })

  it("exposes stop through the workbench imperative handle", async () => {
    const state = sessionState()
    mocks.useSession.mockReturnValue(state)
    const ref = { current: null as null | { stop: () => void } }

    renderWithProviders(
      <AgentWorkbench
        ref={ref}
        sessionId="session-1"
        projectId="project-1"
      />,
    )

    act(() => ref.current?.stop())
    await waitFor(() => expect(state.cancel).toHaveBeenCalledTimes(1))
  })
})
