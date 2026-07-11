import { createRef } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  AgentCoreChat,
  type AgentCoreChatHandle,
} from "@/components/bioinfoflow/agent-core/agent-core-chat"
import { useAgentCore } from "@/hooks/use-agent-core"
import { useLlmSettings } from "@/hooks/use-llm-settings"

const { clearStoredAgentSessionIdMock, modelSelectorPropsMock } = vi.hoisted(() => ({
  clearStoredAgentSessionIdMock: vi.fn(),
  modelSelectorPropsMock: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    const copy: Record<string, Record<string, string>> = {
      accessibility: {
        attachFiles: "Attach files",
        message: "Message",
        selectProject: "Select a project",
        sendMessage: "Send message",
        stopGenerating: "Stop generating",
      },
      agent: {
        disclaimer: "Bioinfoflow Agents can make mistakes. Verify important results.",
      },
      agentCore: {
        acceptMemory: "Accept memory",
        actionApproval: "Approval required",
        actionTimeline: "Action timeline",
        approveAction: "Approve action",
        artifactPanel: "Artifacts",
        assistant: "AgentCore",
        clarificationRequested: "Clarification requested",
        clarificationResolved: "Resolved",
        emptyDescription: "Send a request to create an AgentCore session.",
        emptyTitle: "Start a controlled analysis",
        eventLedger: "Event ledger",
        idle: "Idle",
        loading: "Loading AgentCore sessions...",
        memoryProposals: "Memory proposals",
        noFinalText: "No final response was recorded for this turn.",
        rejectAction: "Reject action",
        rejectMemory: "Reject memory",
        running: "Running",
        selectProjectDescription: "Choose a project from the sidebar.",
        selectProjectTitle: "Select a project",
        session: `Session {id}`,
        sessionPending: "Session will be created on first message",
        title: "AgentCore",
        user: "You",
        auditToggle: "View events",
        modelProfile: "Model profile",
        modelProfileAuto: "Auto model",
        permissionMode: "Tool permissions",
        permissionAskEach: "Ask every time",
        permissionBypass: "Bypass approvals",
        permissionGuarded: "Ask on risk",
        reactionCopy: "Copy response",
        reactionDislike: "Dislike response",
        reactionLike: "Like response",
        reactionMore: "More response actions",
        reactionRegenerate: "Regenerate response",
        quickDiagnose: "Diagnose failure",
        quickPreflight: "Preflight run",
        quickQc: "Review MultiQC",
      },
      chat: {
        "quickStart.askQuestion": "Ask a question",
        "quickStart.askQuestionDescription": "Describe your analysis needs in plain language",
        "quickStart.tryDemo": "Try a demo",
        "quickStart.tryDemoDescription": "Run a pre-configured pipeline",
        "quickStart.upload": "Upload data",
        "quickStart.uploadDescription": "Start with your own FASTQ, BAM, or VCF files",
      },
      greeting: {
        afternoon: "Good morning ☀️ What data shall we explore?",
        evening: "Good morning ☀️ What data shall we explore?",
        lateNight: "Good morning ☀️ What data shall we explore?",
        morning: "Good morning ☀️ What data shall we explore?",
      },
      "settings.modelSelector": {
        auto: "Auto select",
        section: "Routing",
        noProviders: "No model available",
        configure: "Configure providers",
        searchModels: "Search models...",
      },
      executionMode: {
        approveAllDescription: "Also prompt on low-risk writes. Strictest mode.",
        approveAllShort: "Approve all",
        approveAllTitle: "Approve all actions",
        askDescription: "Prompt before running high-risk tools like runs, shell, and code execution.",
        askShort: "Ask",
        askTitle: "Ask (Default)",
        bypassDescription: "Never prompt. The agent runs every tool automatically.",
        bypassShort: "Bypass",
        bypassTitle: "Bypass all approvals",
        changeFailed: "Could not change execution mode.",
        menuLabel: "Tool execution mode",
        triggerAriaLabel: "Change execution mode",
      },
      welcome: {
        blankDescription: "Start empty",
        blankName: "Blank project",
        customProject: "Create custom project",
        eyebrow: "Welcome",
        rnaseqDescription: "RNA-seq",
        rnaseqName: "RNA-seq",
        subtitle: "Create a project to begin.",
        title: "Set up your first bioinformatics workspace",
        wgsDescription: "WGS",
        wgsName: "WGS",
      },
    }
    return (key: string, values?: Record<string, string>) =>
      (copy[namespace]?.[key] ?? key).replace(
        "{id}",
        values?.id ?? "",
      )
  },
}))

vi.mock("@/hooks/use-agent-core", () => ({
  useAgentCore: vi.fn(),
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: vi.fn(),
}))

vi.mock("@/lib/agent-core/session-storage", () => ({
  clearStoredAgentSessionId: (...args: unknown[]) =>
    clearStoredAgentSessionIdMock(...args),
}))

vi.mock("@/components/bioinfoflow/chat/model-selector", () => ({
  ModelSelector: (props: {
    selectedModel: { provider: string; model: string } | null
    onSelectModel: (model: { provider: string; model: string } | null) => void
  }) => {
    modelSelectorPropsMock(props)
    return (
      <button onClick={() => props.onSelectModel(null)}>
        model-selector:{props.selectedModel?.model || "auto"}
      </button>
    )
  },
}))

describe("AgentCoreChat", () => {
  const useAgentCoreMock = vi.mocked(useAgentCore)
  const useLlmSettingsMock = vi.mocked(useLlmSettings)
  const sendTurn = vi.fn()
  const setActiveSessionId = vi.fn()
  const updateSessionSettings = vi.fn()
  const setSelectedModel = vi.fn()
  const approveAction = vi.fn()
  const rejectAction = vi.fn()
  const acceptMemory = vi.fn()
  const rejectMemory = vi.fn()

  beforeEach(() => {
    sendTurn.mockReset()
    setActiveSessionId.mockReset()
    updateSessionSettings.mockReset()
    approveAction.mockReset()
    rejectAction.mockReset()
    acceptMemory.mockReset()
    rejectMemory.mockReset()
    clearStoredAgentSessionIdMock.mockReset()
    modelSelectorPropsMock.mockReset()
    setSelectedModel.mockReset()
    useLlmSettingsMock.mockReturnValue({
      settings: null,
      models: [
        {
          provider: "openai",
          label: "OpenAI",
          models: [
            {
              id: "gpt-5.4",
              name: "GPT-5.4",
              context_window: 200000,
            },
          ],
        },
      ],
      allModels: [
        { id: "gpt-5.4", name: "GPT-5.4", context_window: 200000, provider: "openai" },
      ],
      isLoading: false,
      hasConfiguredProvider: true,
      selectedModel: { provider: "openai", model: "gpt-5.4" },
      updateSettings: vi.fn(),
      setSelectedModel,
      testProvider: vi.fn(),
      refetch: vi.fn(),
    })
    useAgentCoreMock.mockReturnValue({
      sessions: [
        {
          id: "session-12345678",
          project_id: "project-1",
          workspace_id: "workspace-1",
          user_id: "user-1",
          title: "RNA-seq review",
          role_profile: "bioinformatician",
          permission_mode: "guarded_auto",
          automation_mode: "assisted",
          default_model_profile_id: null,
          status: "active",
          metadata: null,
          created_at: "2026-06-04T00:00:00Z",
          updated_at: "2026-06-04T00:00:00Z",
        },
      ],
      activeSession: {
        id: "session-12345678",
        project_id: "project-1",
        workspace_id: "workspace-1",
        user_id: "user-1",
        title: "RNA-seq review",
        role_profile: "bioinformatician",
        permission_mode: "guarded_auto",
        automation_mode: "assisted",
        default_model_profile_id: null,
        status: "active",
        metadata: null,
        created_at: "2026-06-04T00:00:00Z",
        updated_at: "2026-06-04T00:00:00Z",
      },
      activeSessionId: "session-12345678",
      activePermissionMode: "guarded_auto",
      activeModelProfileId: null,
      activeModelSelection: { provider: "openai", model: "gpt-5.4" },
      turns: [
        {
          id: "turn-1",
          session_id: "session-12345678",
          project_id: "project-1",
          workspace_id: "workspace-1",
          user_id: "user-1",
          input_text: "Check FASTQ quality",
          input_parts: null,
          status: "completed",
          model_profile_snapshot: null,
          final_text: "FASTQ pairing and QC look ready for preflight.",
          token_usage: null,
          error_code: null,
          error_message: null,
          created_at: "2026-06-04T00:00:01Z",
          updated_at: "2026-06-04T00:00:01Z",
          started_at: "2026-06-04T00:00:01Z",
          completed_at: "2026-06-04T00:00:02Z",
        },
      ],
      events: [
        {
          id: "event-1",
          session_id: "session-12345678",
          turn_id: "turn-1",
          seq: 1,
          type: "turn.created",
          payload: { input_text: "Check FASTQ quality" },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-04T00:00:01Z",
          updated_at: "2026-06-04T00:00:01Z",
        },
        {
          id: "event-2",
          session_id: "session-12345678",
          turn_id: "turn-1",
          seq: 2,
          type: "assistant.text.completed",
          payload: {
            text: "FASTQ pairing and QC look ready for preflight.",
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-04T00:00:02Z",
          updated_at: "2026-06-04T00:00:02Z",
        },
        {
          id: "event-3",
          session_id: "session-12345678",
          turn_id: "turn-1",
          seq: 3,
          type: "action.waiting_decision",
          payload: {
            action_id: "action-1",
            name: "execution.shell",
            kind: "tool",
            risk_level: "act_high",
            input_preview: "Run command: ls results",
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-04T00:00:03Z",
          updated_at: "2026-06-04T00:00:03Z",
        },
        {
          id: "event-4",
          session_id: "session-12345678",
          turn_id: "turn-1",
          seq: 4,
          type: "user_input.requested",
          payload: {
            request_id: "question-1",
            question: "Which reference genome should I use?",
            options: ["hg19", "hg38"],
            reason: "Reference genome affects alignment and annotation.",
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-04T00:00:04Z",
          updated_at: "2026-06-04T00:00:04Z",
        },
        {
          id: "event-5",
          session_id: "session-12345678",
          turn_id: "turn-1",
          seq: 5,
          type: "user_input.resolved",
          payload: {
            request_id: "question-1",
            answer: "hg38",
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-04T00:00:05Z",
          updated_at: "2026-06-04T00:00:05Z",
        },
      ],
      artifactsByTurn: new Map([
        [
          "turn-1",
          [
            {
              id: "artifact-1",
              session_id: "session-12345678",
              turn_id: "turn-1",
              action_id: "action-1",
              type: "log_summary",
              title: "execution.shell output",
              summary: "Command exited with code 0.",
              payload: {
                stdout: "summary.tsv",
              },
              file_path: null,
              resource_ref: null,
              created_at: "2026-06-04T00:00:04Z",
              updated_at: "2026-06-04T00:00:04Z",
            },
          ],
        ],
      ]),
      proposedMemories: [
        {
          id: "memory-1",
          workspace_id: "workspace-1",
          project_id: "project-1",
          session_id: "session-12345678",
          scope: "project",
          type: "project_convention",
          content: {
            reference_genome: "hg38",
          },
          source: {
            turn_id: "turn-1",
          },
          confidence: 91,
          status: "proposed",
          created_at: "2026-06-04T00:00:05Z",
          updated_at: "2026-06-04T00:00:05Z",
        },
      ],
      isLoading: false,
      status: "idle",
      error: null,
      refreshSessions: vi.fn(),
      refreshTurns: vi.fn(),
      setActiveSessionId,
      updateSessionSettings,
      sendTurn,
      approveAction,
      rejectAction,
      acceptMemory,
      rejectMemory,
    })
  })

  it("sends new user input through AgentCore turns", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Summarize MultiQC" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Send message" }))

    expect(sendTurn).toHaveBeenCalledWith("Summarize MultiQC", {
      modelSelection: { provider: "openai", model: "gpt-5.4" },
    })
  })

  it("restores the explained permission mode menu and updates AgentCore permission_mode", async () => {
    const user = userEvent.setup()
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    await user.click(screen.getByRole("button", { name: "Change execution mode" }))

    expect(await screen.findByText("Tool execution mode")).toBeInTheDocument()
    expect(screen.getByText("Ask (Default)")).toBeInTheDocument()
    expect(screen.getByText("Prompt before running high-risk tools like runs, shell, and code execution.")).toBeInTheDocument()
    expect(screen.getByText("Approve all actions")).toBeInTheDocument()
    expect(screen.getByText("Also prompt on low-risk writes. Strictest mode.")).toBeInTheDocument()
    expect(screen.getByText("Bypass all approvals")).toBeInTheDocument()

    await user.click(screen.getByText("Bypass all approvals"))

    expect(updateSessionSettings).toHaveBeenCalledWith({
      permissionMode: "bypass",
    })
  })

  it("uses configured provider models for the assistant model selector", async () => {
    const user = userEvent.setup()

    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    expect(screen.getAllByText("model-selector:gpt-5.4").length).toBeGreaterThan(0)

    await user.click(screen.getAllByText("model-selector:gpt-5.4")[0]!)

    expect(setSelectedModel).toHaveBeenCalledWith(null)
    expect(modelSelectorPropsMock).toHaveBeenCalled()
  })

  it("renders the project welcome card when no project is selected", () => {
    const onQuickCreateProject = vi.fn()
    const onOpenCreateProjectDialog = vi.fn()

    render(
      <AgentCoreChat
        onQuickCreateProject={onQuickCreateProject}
        onOpenCreateProjectDialog={onOpenCreateProjectDialog}
      />,
    )

    expect(screen.getByText("Set up your first bioinformatics workspace")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Blank project/ })).toBeInTheDocument()
    expect(useAgentCoreMock).toHaveBeenCalledWith(undefined, expect.any(Object))
  })

  it("restores the Gemini-style halo welcome composer when a project has no turns", () => {
    useAgentCoreMock.mockReturnValue({
      ...useAgentCoreMock(),
      activeSession: null,
      activeSessionId: null,
      activePermissionMode: "guarded_auto",
      activeModelProfileId: null,
      turns: [],
      events: [],
      artifactsByTurn: new Map(),
      proposedMemories: [],
    })

    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    expect(screen.getByText("Good morning ☀️ What data shall we explore?")).toBeInTheDocument()
    expect(screen.getByText("Upload data")).toBeInTheDocument()
    expect(screen.getByText("Try a demo")).toBeInTheDocument()
    expect(screen.getByText("Ask a question")).toBeInTheDocument()
    expect(screen.getByText("Bioinfoflow Agents can make mistakes. Verify important results.")).toBeInTheDocument()
    expect(document.querySelector(".agent-halo-surface")).toBeInTheDocument()
    expect(document.querySelector(".agent-center-stage")).toBeInTheDocument()
    expect(screen.queryByText("Start a controlled analysis")).not.toBeInTheDocument()
    expect(screen.queryByText("Session will be created on first message")).not.toBeInTheDocument()
  })

  it("clears the stored project session when starting a new draft from the chat handle", () => {
    const ref = createRef<AgentCoreChatHandle>()

    render(
      <AgentCoreChat
        ref={ref}
        projectId="project-1"
        activeSessionId="session-12345678"
        workspaceEnabled
      />,
    )

    act(() => {
      ref.current?.newConversation()
    })

    expect(setActiveSessionId).toHaveBeenCalledWith(null)
    expect(clearStoredAgentSessionIdMock).toHaveBeenCalledWith("project-1")
  })
})
