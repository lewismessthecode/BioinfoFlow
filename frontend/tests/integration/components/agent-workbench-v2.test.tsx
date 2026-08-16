import { act, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentWorkbench } from "@/components/bioinfoflow/agent/agent-workbench"
import type { AgentSessionState } from "@/hooks/use-agent-session"
import type { HistoryEntry, MessageEntry, SessionSnapshot } from "@/lib/agent/contracts"
import { ApiError } from "@/lib/api"
import { renderWithProviders } from "@/tests/test-utils"

const mocks = vi.hoisted(() => ({
  createSession: vi.fn(),
  dispatchCommand: vi.fn(),
  updateSession: vi.fn(),
  publishSummary: vi.fn(),
  replace: vi.fn(),
  push: vi.fn(),
  useSession: vi.fn(),
  catalogPanel: vi.fn(),
  setSelectedModel: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
}))

vi.mock("@/lib/agent/client", () => ({
  createAgentSession: mocks.createSession,
  dispatchAgentCommand: mocks.dispatchCommand,
  updateAgentSession: mocks.updateSession,
}))

vi.mock("@/lib/agent/session-preferences", () => ({
  publishAgentSessionSummary: mocks.publishSummary,
  sessionSummaryFromView: (session: Record<string, unknown>) => session,
}))

vi.mock("@/hooks/use-agent-session", () => ({
  useAgentSession: (...args: unknown[]) => mocks.useSession(...args),
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: () => ({
    models: [
      {
        provider: "provider-1",
        provider_kind: "openai",
        label: "OpenAI",
        models: [
          {
            id: "gpt-5.6",
            name: "GPT-5.6",
            model_id: "model-record-1",
            context_window: 128000,
            supports_vision: true,
          },
          {
            id: "gpt-5.7",
            name: "GPT-5.7",
            model_id: "model-record-2",
            context_window: 128000,
            supports_vision: true,
          },
        ],
      },
    ],
    selectedModel: {
      provider: "provider-1",
      model: "gpt-5.6",
      model_id: "model-record-1",
    },
    setSelectedModel: mocks.setSelectedModel,
    isLoading: false,
  }),
}))

vi.mock("@/components/bioinfoflow/chat/model-selector", () => ({
  ModelSelector: ({
    disabled,
    onSelectModel,
  }: {
    disabled?: boolean
    onSelectModel: (selection: {
      provider: string
      model: string
      model_id: string
    }) => void
  }) => (
    <button
      type="button"
      disabled={disabled}
      onClick={() =>
        onSelectModel({
          provider: "provider-1",
          model: "gpt-5.7",
          model_id: "model-record-2",
        })
      }
    >
      GPT-5.6 model selector
    </button>
  ),
}))

vi.mock("@/components/bioinfoflow/agent/agent-context-picker", () => ({
  AgentContextPicker: ({ ensureSession }: { ensureSession: () => Promise<string> }) => (
    <button type="button" onClick={() => void ensureSession()}>
      Add context
    </button>
  ),
}))

vi.mock("@/components/bioinfoflow/agent/agent-transcript", () => ({
  AgentTranscript: ({
    entries,
    onRetryMessage,
    onEditMessage,
  }: {
    entries: HistoryEntry[]
    onRetryMessage?: (entry: MessageEntry) => void | Promise<void>
    onEditMessage?: (entry: MessageEntry) => void
  }) => (
    <div data-testid="transcript">
      entries:{entries.length}
      {entries.map((entry) =>
        entry.type === "message" && entry.payload.role === "assistant" ? (
          <button key={entry.id} type="button" onClick={() => void onRetryMessage?.(entry)}>
            Retry transcript message
          </button>
        ) : entry.type === "message" && entry.payload.role === "user" ? (
          <button key={entry.id} type="button" onClick={() => onEditMessage?.(entry)}>
            Edit transcript message
          </button>
        ) : null,
      )}
    </div>
  ),
}))

vi.mock("@/components/bioinfoflow/settings/llm-catalog-panel", () => ({
  LlmCatalogPanel: () => {
    mocks.catalogPanel()
    return <div>Model catalog panel</div>
  },
}))

vi.mock("@/components/bioinfoflow/agent/agent-composer", () => ({
  AgentComposer: ({
    onSendMessage,
    onSteer,
    onCancel,
    permissionMode,
    onPermissionModeChange,
    contextControls,
    disabled,
    placement,
    modelControls,
    initialValue,
    contextInputs = [],
  }: {
    onSendMessage: (parts: [{ type: "text"; text: string }]) => Promise<void>
    onSteer: (parts: [{ type: "text"; text: string }]) => Promise<void>
    onCancel: () => Promise<void>
    permissionMode: string
    onPermissionModeChange: (mode: "full_access") => Promise<void>
    contextControls: ReactNode
    disabled?: boolean
    placement?: "draft" | "dock"
    modelControls?: ReactNode
    initialValue?: string
    contextInputs?: Array<{ label: string }>
  }) => (
    <div data-testid="mock-composer" data-placement={placement}>
      {contextControls}
      {modelControls}
      <input aria-label="Draft message" defaultValue={initialValue || "Keep this draft"} />
      <span data-testid="composer-context-count">{contextInputs.length}</span>
      <span>Permission: {permissionMode}</span>
      <button
        type="button"
        disabled={disabled}
        onClick={() => void onPermissionModeChange("full_access")}
      >
        Change permission
      </button>
      <button
        type="button"
        onClick={() =>
          void onSendMessage([{ type: "text", text: "Hello" }]).catch(
            () => {},
          )
        }
      >
        Send message
      </button>
      <button
        type="button"
        onClick={() =>
          void onSteer([{ type: "text", text: "Continue" }]).catch(() => {})
        }
      >
        Steer message
      </button>
      <button type="button" onClick={() => onCancel()}>
        Stop run
      </button>
    </div>
  ),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => "en",
}))

vi.mock("@/hooks/use-agent-ui-bootstrap", () => ({
  useAgentUiBootstrap: () => ({
    isLoading: false,
    bootstrap: {
      protocolVersion: 1,
      capabilities: {
        reasoning: true,
        toolActivity: true,
        approvals: true,
        artifacts: true,
        starterPrompts: true,
        multiTargetExecution: false,
        retry: true,
        editAndResend: true,
      },
      executionTargets: [
        {
          id: "local",
          handle: "local",
          alias: "Local",
          kind: "local",
          status: "online",
          primary: true,
          disabledReason: null,
        },
      ],
      executionScope: { mode: "auto", targetIds: [] },
      starterPrompts: [],
      composerHint: null,
      degradedReason: null,
    },
  }),
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
        catalog_model_id: "model-record-1",
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
  }
}

function sessionState(
  overrides: Partial<AgentSessionState> = {},
): AgentSessionState {
  return {
    session: snapshot().session,
    runs: [],
    entries: [],
    activeRun: null,
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
    mocks.updateSession.mockReset()
    mocks.publishSummary.mockReset()
    mocks.replace.mockReset()
    mocks.push.mockReset()
    mocks.useSession.mockReset()
    mocks.catalogPanel.mockReset()
    mocks.setSelectedModel.mockReset()
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
      modelId: "model-record-1",
      executionScope: { mode: "auto", target_ids: [] },
    })
    expect(mocks.dispatchCommand).toHaveBeenCalledWith(
      "session-1",
      expect.objectContaining({
        type: "message",
        parts: [{ type: "text", text: "Hello" }],
        run_settings: {
          permission_mode: "ask_dangerous",
          execution_scope: { mode: "auto", target_ids: [] },
        },
      }),
    )
    expect(mocks.publishSummary).toHaveBeenCalled()
    expect(mocks.replace).toHaveBeenCalledWith("/agent/session-1")
  })

  it("centers the new-conversation entry and docks the composer after a session exists", () => {
    const view = renderWithProviders(
      <AgentWorkbench sessionId={null} projectId="project-1" />,
    )

    expect(screen.getByTestId("agent-draft-entry")).toBeInTheDocument()
    expect(screen.getByTestId("mock-composer")).toHaveAttribute(
      "data-placement",
      "draft",
    )
    expect(screen.getByRole("button", { name: "GPT-5.6 model selector" })).toBeEnabled()
    expect(screen.queryByRole("heading", { name: "newConversation" })).not.toBeInTheDocument()

    view.rerender(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.getByTestId("mock-composer")).toHaveAttribute(
      "data-placement",
      "dock",
    )
  })

  it("opens inline model connection without discarding the draft", async () => {
    const user = userEvent.setup()
    mocks.createSession.mockRejectedValue(
      new ApiError("Configuration required", {
        code: "AGENT_MODEL_REQUIRED",
        status: 422,
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId={null} projectId="project-1" />,
    )

    await user.click(screen.getByRole("button", { name: "Send message" }))

    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveAccessibleName("modelConnection.title")
    expect(dialog).toHaveTextContent(
      "modelConnection.description",
    )
    expect(await screen.findByText("Model catalog panel")).toBeInTheDocument()
    await waitFor(() => expect(mocks.catalogPanel).toHaveBeenCalledTimes(1))
    expect(
      screen.getByRole("link", { name: "modelConnection.fullSettings" }),
    ).toMatchObject({
      href: expect.stringContaining("/settings?section=providers"),
      target: "_blank",
    })

    await user.keyboard("{Escape}")

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByRole("textbox", { name: "Draft message" })).toHaveValue(
      "Keep this draft",
    )
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("does not infer model setup from a generic validation message", async () => {
    const user = userEvent.setup()
    mocks.createSession.mockRejectedValue(
      new ApiError("The model selector is invalid", {
        code: "VALIDATION_ERROR",
        status: 422,
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId={null} projectId="project-1" />,
    )

    await user.click(screen.getByRole("button", { name: "Send message" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("createError")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(mocks.catalogPanel).not.toHaveBeenCalled()
  })

  it.each([
    ["sendMessage", "Send message"],
    ["steer", "Steer message"],
  ] as const)(
    "opens inline model connection when an existing session cannot %s",
    async (method, buttonName) => {
      const user = userEvent.setup()
      const state = sessionState({
        [method]: vi.fn().mockRejectedValue(
          new ApiError("Configuration required", {
            code: "AGENT_MODEL_REQUIRED",
            status: 422,
          }),
        ),
      })
      mocks.useSession.mockReturnValue(state)

      renderWithProviders(
        <AgentWorkbench sessionId="session-1" projectId="project-1" />,
      )

      await user.click(screen.getByRole("button", { name: buttonName }))

      expect(await screen.findByRole("dialog")).toHaveAccessibleName(
        "modelConnection.title",
      )
      await user.keyboard("{Escape}")
      expect(screen.getByRole("textbox", { name: "Draft message" })).toHaveValue(
        "Keep this draft",
      )
    },
  )

  it("persists permission changes after context upload creates a draft session", async () => {
    const user = userEvent.setup()
    const created = snapshot()
    const updated = snapshot()
    updated.session.permission_mode = "full_access"
    mocks.createSession.mockResolvedValue(created)
    mocks.updateSession.mockResolvedValue(updated)

    renderWithProviders(
      <AgentWorkbench sessionId={null} projectId="project-1" />,
    )

    await user.click(screen.getByRole("button", { name: "Add context" }))
    await waitFor(() => expect(mocks.createSession).toHaveBeenCalledTimes(1))

    await user.click(
      screen.getByRole("button", { name: "Change permission" }),
    )

    await waitFor(() =>
      expect(mocks.updateSession).toHaveBeenCalledWith("session-1", {
        permissionMode: "full_access",
      }),
    )
    expect(screen.getByText("Permission: full_access")).toBeInTheDocument()
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
    expect(screen.getByTestId("agent-header-model")).toHaveTextContent("GPT-5.6")
    expect(screen.getByText("emptyTitle")).toBeInTheDocument()
    expect(screen.getByText("connection.reconnecting")).toBeInTheDocument()
  })

  it("renders an injected session through the formal workbench without opening a live transport", () => {
    const injectedState = sessionState({
      entries: [
        {
          id: "assistant-demo",
          session_id: "session-1",
          run_id: null,
          sequence: 1,
          schema_version: 2,
          created_at: timestamp,
          type: "message",
          payload: {
            role: "assistant",
            parts: [{ id: "text-demo", type: "text", text: "Demo replay" }],
          },
        },
      ],
    })

    renderWithProviders(
      <AgentWorkbench
        sessionId="session-1"
        projectId="project-1"
        sessionState={injectedState}
        interactive={false}
      />,
    )

    expect(screen.getByTestId("agent-workbench")).toBeInTheDocument()
    expect(screen.getByTestId("transcript")).toHaveTextContent("entries:1")
    expect(
      screen.getByRole("button", { name: "Change permission" }),
    ).toBeDisabled()
    expect(mocks.useSession).not.toHaveBeenCalled()
  })

  it("keeps the model visible and removes healthy connection noise", () => {
    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.getByTestId("agent-header-model")).toHaveTextContent("GPT-5.6")
    expect(screen.queryByLabelText("connection.connected")).not.toBeInTheDocument()
  })

  it("updates the live model default and freezes it into the next message", async () => {
    const user = userEvent.setup()
    const state = sessionState()
    mocks.useSession.mockReturnValue(state)
    mocks.updateSession.mockResolvedValue(snapshot())

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    await user.click(
      screen.getByRole("button", { name: "GPT-5.6 model selector" }),
    )
    await waitFor(() =>
      expect(mocks.updateSession).toHaveBeenCalledWith("session-1", {
        modelId: "model-record-2",
      }),
    )

    await user.click(screen.getByRole("button", { name: "Send message" }))

    expect(state.sendMessage).toHaveBeenCalledWith(
      [{ type: "text", text: "Hello" }],
      {
        model: { model_id: "model-record-2" },
        permission_mode: "ask_dangerous",
        execution_scope: { mode: "auto", target_ids: [] },
      },
    )
  })

  it("retries the canonical user input as a normal message with current Run settings", async () => {
    const user = userEvent.setup()
    const state = sessionState({
      entries: conversationEntries(),
    })
    mocks.useSession.mockReturnValue(state)

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    await user.click(
      screen.getByRole("button", { name: "Retry transcript message" }),
    )

    expect(state.sendMessage).toHaveBeenCalledWith(
      [
        { type: "file_ref", project_id: "project-1", path: "results/counts.tsv" },
        { type: "text", text: "Compare these files" },
      ],
      {
        model: { model_id: "model-record-1" },
        permission_mode: "ask_dangerous",
        execution_scope: { mode: "auto", target_ids: [] },
      },
    )
  })

  it("edits canonical user text and references in the Composer without dispatching", async () => {
    const user = userEvent.setup()
    const state = sessionState({ entries: conversationEntries() })
    mocks.useSession.mockReturnValue(state)

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    await user.click(
      screen.getByRole("button", { name: "Edit transcript message" }),
    )

    expect(screen.getByRole("textbox", { name: "Draft message" })).toHaveValue(
      "Compare these files",
    )
    expect(screen.getByTestId("composer-context-count")).toHaveTextContent("1")
    expect(state.sendMessage).not.toHaveBeenCalled()
  })

  it.each(["archived", "closing", "deleted"] as const)(
    "explains why a %s conversation is read-only and disables permission changes",
    (status) => {
      mocks.useSession.mockReturnValue(
        sessionState({
          session: { ...snapshot().session, status },
        }),
      )

      renderWithProviders(
        <AgentWorkbench sessionId="session-1" projectId="project-1" />,
      )

      expect(screen.getByRole("status")).toHaveTextContent(
        `readOnly.${status}`,
      )
      expect(
        screen.getByRole("button", { name: "Change permission" }),
      ).toBeDisabled()
    },
  )

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

function conversationEntries(): HistoryEntry[] {
  return [
    {
      id: "message-user",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 1,
      schema_version: 2,
      created_at: timestamp,
      type: "message",
      payload: {
        role: "user",
        parts: [
          {
            id: "file-ref",
            type: "file_ref",
            label: "counts.tsv",
            project_id: "project-1",
            path: "results/counts.tsv",
          },
          { id: "user-text", type: "text", text: "Compare these files" },
        ],
      },
    },
    {
      id: "message-assistant",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 2,
      schema_version: 2,
      created_at: timestamp,
      type: "message",
      payload: {
        role: "assistant",
        parts: [{ id: "assistant-text", type: "text", text: "They match." }],
      },
    },
  ]
}
