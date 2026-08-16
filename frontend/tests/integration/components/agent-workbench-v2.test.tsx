import { act, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  AgentWorkbench,
  type AgentWorkbenchHandle,
} from "@/components/bioinfoflow/agent/agent-workbench"
import type { AgentSessionState } from "@/hooks/use-agent-session"
import type { ConversationViewModel } from "@/lib/agent/conversation-model/types"
import type { SessionSnapshot } from "@/lib/agent/contracts"
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
  fetchRemoteConnections: vi.fn(),
  useStarterPrompts: vi.fn(),
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

vi.mock("@/hooks/use-agent-starter-prompts", () => ({
  useAgentStarterPrompts: (...args: unknown[]) =>
    mocks.useStarterPrompts(...args),
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
        ],
      },
      {
        provider: "provider-2",
        provider_kind: "anthropic",
        label: "Anthropic",
        models: [
          {
            id: "claude-sonnet",
            name: "Claude Sonnet",
            model_id: "model-record-2",
            context_window: 200000,
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

vi.mock("@/lib/demo-connections", () => ({
  fetchRemoteConnections: (...args: unknown[]) =>
    mocks.fetchRemoteConnections(...args),
}))

vi.mock("@/components/bioinfoflow/chat/model-selector", () => ({
  ModelSelector: ({
    disabled,
    selectedModel,
    onSelectModel,
  }: {
    disabled?: boolean
    selectedModel?: { provider?: string | null; model?: string | null } | null
    onSelectModel: (selection: {
      provider: string
      model: string
      model_id: string
    }) => void
  }) => (
    <button
      type="button"
      disabled={disabled}
      data-selected-provider={selectedModel?.provider ?? ""}
      onClick={() =>
        onSelectModel({
          provider: "provider-2",
          model: "claude-sonnet",
          model_id: "model-record-2",
        })
      }
    >
      {selectedModel?.model ?? "GPT-5.6"} model selector
    </button>
  ),
}))

vi.mock("@/components/bioinfoflow/agent/agent-context-picker", () => ({
  AgentContextPicker: ({
    ensureSession,
  }: {
    ensureSession: () => Promise<string>
  }) => (
    <button type="button" onClick={() => void ensureSession()}>
      Add context
    </button>
  ),
}))

vi.mock("@/components/bioinfoflow/agent/conversation-transcript", () => ({
  ConversationTranscript: ({ view }: { view: ConversationViewModel }) => (
    <div data-testid="transcript">
      blocks:{view.transcript.length}:
      {view.transcript
        .map((block) => (block.type === "message" ? block.text : block.type))
        .join("|")}
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
  AgentCommandDiscoveryHint: ({ visible }: { visible: boolean }) =>
    visible ? <div data-testid="mock-command-discovery-hint" /> : null,
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
    environmentSelection,
    environmentTargets,
    environmentSelectionPending,
    onEnvironmentSelectionChange,
    starterPrompts,
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
    environmentSelection?: { mode: "auto" | "manual" }
    environmentTargets?: readonly { id: string; label: string }[]
    environmentSelectionPending?: boolean
    onEnvironmentSelectionChange?: (selection: {
      mode: "manual"
      targetIds: string[]
    }) => Promise<void>
    starterPrompts?: readonly string[]
  }) => (
    <div data-testid="mock-composer" data-placement={placement}>
      {contextControls}
      {modelControls}
      <input aria-label="Draft message" defaultValue="Keep this draft" />
      <span>Permission: {permissionMode}</span>
      <span>Environment: {environmentSelection?.mode}</span>
      <span>Environment targets: {environmentTargets?.length ?? 0}</span>
      <span>Environment pending: {String(environmentSelectionPending)}</span>
      {starterPrompts?.map((prompt) => (
        <span key={prompt}>{prompt}</span>
      ))}
      <button
        type="button"
        disabled={disabled}
        onClick={() =>
          void onEnvironmentSelectionChange?.({
            mode: "manual",
            targetIds: ["local", "gpu-01"],
          }).catch(() => {})
        }
      >
        Choose manual environments
      </button>
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
          void onSendMessage([{ type: "text", text: "Hello" }]).catch(() => {})
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
      settings_revision: 1,
      environment_scope: { mode: "auto", environment_ids: null },
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
    conversationView: conversationView([]),
    connectionStatus: "connected",
    error: null,
    isLoading: false,
    sendMessage: vi.fn().mockResolvedValue(undefined),
    steer: vi.fn().mockResolvedValue(undefined),
    respond: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn().mockResolvedValue(undefined),
    updatePermissionMode: vi.fn().mockResolvedValue(undefined),
    updateModel: vi.fn().mockResolvedValue(undefined),
    updateEnvironmentScope: vi.fn().mockResolvedValue(undefined),
    retry: vi.fn(),
    ...overrides,
  }
}

function conversationView(
  transcript: ConversationViewModel["transcript"],
  activeWork: ConversationViewModel["activeWork"] = null,
): ConversationViewModel {
  return {
    protocolVersion: 1,
    conversation: {
      id: "session-1",
      title: "Variant review",
      status: "active",
      workspaceId: "workspace-1",
      projectId: "project-1",
    },
    composer: {
      placement: transcript.length > 0 || activeWork ? "docked" : "centered",
      canSend: true,
      settings: {
        model: {
          provider: "openai",
          model: "gpt-5.6",
          displayName: "GPT-5.6",
        },
        permissionMode: "ask_dangerous",
        workspaceAccess: "read_write",
        revision: 1,
        environmentScope: { mode: "auto", environmentIds: [] },
      },
      capabilities: {
        modelSelection: true,
        permissionSelection: true,
        environmentSelection: { auto: true, manualMultiSelect: true },
        planMode: false,
      },
    },
    transcript,
    runs: [],
    activeWork,
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
    mocks.fetchRemoteConnections.mockReset()
    mocks.useStarterPrompts.mockReset()
    mocks.useStarterPrompts.mockReturnValue({
      prompts: ["Review the generated project fingerprint"],
      source: "cache",
      refreshPending: false,
      isLoading: false,
      error: null,
    })
    mocks.fetchRemoteConnections.mockImplementation(
      () => new Promise(() => {}),
    )
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

    await user.click(
      screen.getByRole("button", { name: "Choose manual environments" }),
    )
    await user.click(screen.getByRole("button", { name: "Send message" }))

    await waitFor(() => expect(mocks.createSession).toHaveBeenCalledTimes(1))
    expect(mocks.createSession).toHaveBeenCalledWith({
      projectId: "project-1",
      permissionMode: "ask_dangerous",
      workspaceAccess: "read_write",
      modelId: "model-record-1",
      environmentScope: {
        mode: "manual",
        selected_environment_ids: ["local", "gpu-01"],
      },
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

  it("centers the new-conversation entry and docks the composer after a session exists", () => {
    const view = renderWithProviders(
      <AgentWorkbench sessionId={null} projectId="project-1" />,
    )

    expect(screen.getByTestId("agent-draft-entry")).toHaveClass(
      "agent-halo-surface",
    )
    expect(screen.getByTestId("agent-draft-stage")).toHaveClass(
      "agent-center-stage",
      "max-w-[42rem]",
      "-translate-y-8",
    )
    expect(screen.queryByRole("banner")).not.toBeInTheDocument()
    expect(screen.getByTestId("mock-composer")).toHaveAttribute(
      "data-placement",
      "draft",
    )
    expect(
      screen.getByRole("button", { name: "gpt-5.6 model selector" }),
    ).toBeEnabled()
    expect(screen.getByText("Environment: auto")).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "emptyTitle", level: 1 }),
    ).toHaveClass(
      "mb-4",
      "text-[15px]",
      "font-medium",
      "tracking-normal",
      "text-muted-foreground",
    )
    expect(screen.queryByText("emptyDescription")).not.toBeInTheDocument()
    expect(screen.queryByText("capabilityHint")).not.toBeInTheDocument()
    expect(
      screen.getByText("Review the generated project fingerprint"),
    ).toBeInTheDocument()
    expect(mocks.useStarterPrompts).toHaveBeenCalledWith("project-1", "en")
    expect(
      screen.queryByRole("heading", { name: "newConversation" }),
    ).not.toBeInTheDocument()

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
    expect(dialog).toHaveTextContent("modelConnection.description")
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
      expect(
        screen.getByRole("textbox", { name: "Draft message" }),
      ).toHaveValue("Keep this draft")
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

    await user.click(screen.getByRole("button", { name: "Change permission" }))

    await waitFor(() =>
      expect(mocks.updateSession).toHaveBeenCalledWith("session-1", {
        permissionMode: "full_access",
      }),
    )
    expect(screen.getByText("Permission: full_access")).toBeInTheDocument()
  })

  it("keeps model and environment editable after context creates a draft session", async () => {
    const user = userEvent.setup()
    mocks.createSession.mockResolvedValue(snapshot())
    mocks.updateSession.mockImplementation(
      async (_sessionId: string, updates: Record<string, unknown>) => {
        const updated = snapshot()
        if (updates.model) {
          updated.session.model = {
            provider: "anthropic",
            model: "claude-sonnet",
            display_name: "Claude Sonnet",
            supports_vision: true,
            supports_reasoning: true,
            supports_tools: true,
          }
        }
        if (updates.environmentScope) {
          updated.session.environment_scope = {
            mode: "manual",
            environment_ids: ["local", "gpu-01"],
          }
        }
        return updated
      },
    )

    renderWithProviders(
      <AgentWorkbench sessionId={null} projectId="project-1" />,
    )

    await user.click(screen.getByRole("button", { name: "Add context" }))
    await waitFor(() => expect(mocks.createSession).toHaveBeenCalledTimes(1))

    const modelSelector = screen.getByRole("button", {
      name: "gpt-5.6 model selector",
    })
    expect(modelSelector).toBeEnabled()
    await user.click(modelSelector)
    await user.click(
      screen.getByRole("button", { name: "Choose manual environments" }),
    )

    await waitFor(() =>
      expect(mocks.updateSession).toHaveBeenCalledWith("session-1", {
        model: { modelId: "model-record-2" },
      }),
    )
    expect(mocks.updateSession).toHaveBeenCalledWith("session-1", {
      environmentScope: {
        mode: "manual",
        selected_environment_ids: ["local", "gpu-01"],
      },
    })
  })

  it("keeps stream interruptions visible without rendering a conversation title header", () => {
    mocks.useSession.mockReturnValue(
      sessionState({
        connectionStatus: "reconnecting",
        error: new Error("Agent event stream disconnected"),
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.queryByRole("heading", { name: "Variant review" })).not.toBeInTheDocument()
    expect(screen.queryByTestId("agent-header-model")).not.toBeInTheDocument()
    expect(screen.queryByRole("banner")).not.toBeInTheDocument()
    expect(screen.getByText("emptyTitle")).toBeInTheDocument()
    expect(screen.getByText("connection.reconnecting")).toBeInTheDocument()
    const status = screen.getByRole("status", {
      name: "connection.reconnecting",
    })
    expect(status).not.toHaveClass("absolute")
    expect(status.parentElement).toHaveClass("shrink-0", "justify-end")
  })

  it("does not show next-run helper copy while an active run is using earlier settings", () => {
    mocks.useSession.mockReturnValue(
      sessionState({
        conversationView: conversationView([], {
          runId: "run-active",
          status: "running",
          phase: "model",
          startedAt: timestamp,
        }),
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.queryByText("permission.nextRun")).not.toBeInTheDocument()
    expect(screen.getByTestId("mock-composer")).toHaveAttribute(
      "data-placement",
      "dock",
    )
  })

  it("does not rebuild an injected session from legacy transport state when its stable view is unavailable", () => {
    const injectedState = sessionState({
      conversationView: null,
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
    expect(screen.queryByTestId("transcript")).not.toBeInTheDocument()
    expect(screen.getByText("loadErrorTitle")).toBeInTheDocument()
    expect(screen.getByText("loadErrorDescription")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Change permission" }),
    ).toBeDisabled()
    expect(mocks.useSession).not.toHaveBeenCalled()
  })

  it("renders live transcript content only from the stable conversation view", () => {
    mocks.useSession.mockReturnValue(
      sessionState({
        entries: [],
        conversationView: conversationView([
          {
            type: "message",
            id: "stable-message",
            runId: "run-1",
            createdAt: timestamp,
            role: "assistant",
            text: "Stable presentation text",
            references: [],
            streaming: false,
          },
        ]),
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.getByTestId("transcript")).toHaveTextContent(
      "blocks:1:Stable presentation text",
    )
    expect(screen.queryByText("emptyTitle")).not.toBeInTheDocument()
  })

  it("derives the empty state from the stable conversation view", () => {
    mocks.useSession.mockReturnValue(
      sessionState({
        entries: [
          {
            id: "stale-entry",
            session_id: "session-1",
            run_id: null,
            sequence: 1,
            schema_version: 2,
            created_at: timestamp,
            type: "message",
            payload: {
              role: "assistant",
              parts: [{ id: "text", type: "text", text: "Stale transport" }],
            },
          },
        ],
        conversationView: conversationView([]),
      }),
    )

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.getByText("emptyTitle")).toBeInTheDocument()
    expect(screen.queryByTestId("transcript")).not.toBeInTheDocument()
  })

  it("keeps model controls in the composer instead of a duplicate canvas header", () => {
    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(screen.queryByTestId("agent-header-model")).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "gpt-5.6 model selector" }),
    ).toBeInTheDocument()
    expect(
      screen.queryByLabelText("connection.connected"),
    ).not.toBeInTheDocument()
  })

  it("publishes refreshed session titles for the sidebar without rendering them in the canvas", () => {
    const initial = sessionState()
    mocks.useSession.mockReturnValue(initial)
    const view = renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(mocks.publishSummary).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Variant review" }),
    )
    mocks.publishSummary.mockClear()

    const refreshedSession = {
      ...snapshot().session,
      title: "RNA-seq QC Plan",
      updated_at: "2026-08-15T00:00:03Z",
    }
    mocks.useSession.mockReturnValue(
      sessionState({ session: refreshedSession }),
    )
    view.rerender(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    expect(mocks.publishSummary).toHaveBeenCalledWith(
      expect.objectContaining({ title: "RNA-seq QC Plan" }),
    )
    expect(
      screen.queryByRole("heading", { name: "RNA-seq QC Plan" }),
    ).not.toBeInTheDocument()
  })

  it("accepts an interactive conversation model control from the turn-settings adapter", () => {
    renderWithProviders(
      <AgentWorkbench
        sessionId="session-1"
        projectId="project-1"
        conversationModelControls={
          <button type="button">Change GPT-5.6 model</button>
        }
      />,
    )

    expect(
      screen.getByRole("button", { name: "Change GPT-5.6 model" }),
    ).toBeEnabled()
  })

  it("wires live model, permission, and environment changes to sticky session settings", async () => {
    const user = userEvent.setup()
    const state = sessionState()
    mocks.useSession.mockReturnValue(state)
    mocks.fetchRemoteConnections.mockResolvedValue([
      {
        id: "gpu-01",
        name: "GPU 01",
        host: "gpu-01.example.test",
        port: 22,
        username: "bio",
        auth_method: "agent",
        ssh_alias: "gpu-01",
        key_path: "",
        status: "online",
        skill_instructions: "",
      },
    ])

    renderWithProviders(
      <AgentWorkbench sessionId="session-1" projectId="project-1" />,
    )

    await waitFor(() =>
      expect(screen.getByText("Environment targets: 2")).toBeInTheDocument(),
    )
    const modelSelector = screen.getByRole("button", {
      name: "gpt-5.6 model selector",
    })
    expect(modelSelector).toHaveAttribute("data-selected-provider", "provider-1")
    await user.click(modelSelector)
    await user.click(screen.getByRole("button", { name: "Change permission" }))
    await user.click(
      screen.getByRole("button", { name: "Choose manual environments" }),
    )

    expect(state.updateModel).toHaveBeenCalledWith({
      modelId: "model-record-2",
    })
    expect(state.updatePermissionMode).toHaveBeenCalledWith("full_access")
    expect(state.updateEnvironmentScope).toHaveBeenCalledWith({
      mode: "manual",
      selected_environment_ids: ["local", "gpu-01"],
    })
    expect(screen.getByText("Environment pending: true")).toBeInTheDocument()
  })

  it.each(["archived", "closing", "deleted"] as const)(
    "explains why a %s conversation is read-only and disables permission changes",
    (status) => {
      mocks.useSession.mockReturnValue(
        sessionState({
          session: { ...snapshot().session, status },
          conversationView: {
            ...conversationView([]),
            conversation: { ...conversationView([]).conversation, status },
          },
        }),
      )

      renderWithProviders(
        <AgentWorkbench sessionId="session-1" projectId="project-1" />,
      )

      expect(screen.getByRole("status")).toHaveTextContent(`readOnly.${status}`)
      expect(
        screen.getByRole("button", { name: "Change permission" }),
      ).toBeDisabled()
    },
  )

  it("exposes stop through the workbench imperative handle", async () => {
    const state = sessionState()
    mocks.useSession.mockReturnValue(state)
    const ref = { current: null as AgentWorkbenchHandle | null }

    renderWithProviders(
      <AgentWorkbench ref={ref} sessionId="session-1" projectId="project-1" />,
    )

    act(() => ref.current?.stop())
    await waitFor(() => expect(state.cancel).toHaveBeenCalledTimes(1))
  })

  it("starts a new conversation through the workbench imperative handle", () => {
    const onActiveSessionIdChange = vi.fn()
    const ref = { current: null as AgentWorkbenchHandle | null }

    renderWithProviders(
      <AgentWorkbench
        ref={ref}
        sessionId="session-1"
        projectId="project-1"
        onActiveSessionIdChange={onActiveSessionIdChange}
      />,
    )

    act(() => ref.current?.newConversation())

    expect(onActiveSessionIdChange).toHaveBeenCalledWith("")
    expect(mocks.push).toHaveBeenCalledWith("/agent")
  })
})
