import { createRef } from "react"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  AgentCoreChat,
  type AgentCoreChatHandle,
} from "@/components/bioinfoflow/agent-core/agent-core-chat"
import { useAgentCore } from "@/hooks/use-agent-core"
import { useLlmCatalog } from "@/hooks/use-llm-catalog"

const { clearStoredAgentSessionIdMock } = vi.hoisted(() => ({
  clearStoredAgentSessionIdMock: vi.fn(),
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

vi.mock("@/hooks/use-llm-catalog", () => ({
  useLlmCatalog: vi.fn(),
}))

vi.mock("@/lib/agent-core/session-storage", () => ({
  clearStoredAgentSessionId: (...args: unknown[]) =>
    clearStoredAgentSessionIdMock(...args),
}))

describe("AgentCoreChat", () => {
  const useAgentCoreMock = vi.mocked(useAgentCore)
  const useLlmCatalogMock = vi.mocked(useLlmCatalog)
  const sendTurn = vi.fn()
  const setActiveSessionId = vi.fn()
  const updateSessionSettings = vi.fn()
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
    useLlmCatalogMock.mockReturnValue({
      providers: [],
      models: [
        {
          id: "model-1",
          provider_id: "provider-1",
          model_id: "bio-coder",
          display_name: "Bio Coder",
          supports_tools: true,
          supports_streaming: true,
          supports_vision: false,
          supports_json_schema: true,
          supports_reasoning: true,
          created_at: "2026-06-04T00:00:00Z",
          updated_at: "2026-06-04T00:00:00Z",
        },
      ],
      profiles: [
        {
          id: "profile-1",
          name: "Bio Agent",
          task_type: "agent_core",
          primary_model_id: "model-1",
          fallback_model_ids: null,
          scope: "user",
          enabled: true,
          created_at: "2026-06-04T00:00:00Z",
          updated_at: "2026-06-04T00:00:00Z",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      createProvider: vi.fn(),
      setProviderEnabled: vi.fn(),
      testProvider: vi.fn(),
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

  it("renders AgentCore turns with collapsed event audit", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    expect(screen.queryByText("Session session-")).not.toBeInTheDocument()
    expect(screen.queryByText("You")).not.toBeInTheDocument()
    expect(screen.queryByText("AgentCore")).not.toBeInTheDocument()
    expect(screen.getByText("Check FASTQ quality")).toBeInTheDocument()
    expect(
      screen.getByText("FASTQ pairing and QC look ready for preflight."),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Like response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Dislike response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Regenerate response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Copy response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "More response actions" })).toBeInTheDocument()
    expect(screen.getByText("View events")).toBeInTheDocument()
    expect(screen.queryByText("Event ledger")).not.toBeInTheDocument()
    fireEvent.click(screen.getByText("View events"))
    expect(screen.getByText("Event ledger")).toBeInTheDocument()
    expect(screen.getByText("turn.created")).toBeInTheDocument()
    expect(screen.getByText("assistant.text.completed")).toBeInTheDocument()
  })

  it("renders user clarification requests from AgentCore events", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    expect(screen.getByText("Clarification requested")).toBeInTheDocument()
    expect(screen.getByText("Which reference genome should I use?")).toBeInTheDocument()
    expect(screen.getByText("Reference genome affects alignment and annotation.")).toBeInTheDocument()
    expect(screen.getByText("hg19")).toBeInTheDocument()
    expect(screen.getAllByText("hg38").length).toBeGreaterThan(0)
    expect(screen.getByText("Resolved")).toBeInTheDocument()
  })

  it("renders action approvals, artifacts, and memory proposals", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    expect(screen.getByText("Action timeline")).toBeInTheDocument()
    expect(screen.getByText("Approval required")).toBeInTheDocument()
    expect(screen.getByText("execution.shell")).toBeInTheDocument()
    expect(screen.getByText("act_high")).toBeInTheDocument()
    expect(screen.getByText("Run command: ls results")).toBeInTheDocument()
    expect(screen.getByText("Artifacts")).toBeInTheDocument()
    expect(screen.getByText("execution.shell output")).toBeInTheDocument()
    expect(screen.getByText("Command exited with code 0.")).toBeInTheDocument()
    expect(screen.getByText("Memory proposals")).toBeInTheDocument()
    expect(screen.getByText("project_convention")).toBeInTheDocument()
    expect(screen.getByText(/reference_genome/)).toBeInTheDocument()
  })

  it("dispatches action and memory decisions", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    fireEvent.click(screen.getByRole("button", { name: "Approve action" }))
    fireEvent.click(screen.getByRole("button", { name: "Reject action" }))
    fireEvent.click(screen.getByRole("button", { name: "Accept memory" }))
    fireEvent.click(screen.getByRole("button", { name: "Reject memory" }))

    expect(approveAction).toHaveBeenCalledWith("action-1")
    expect(rejectAction).toHaveBeenCalledWith("action-1")
    expect(acceptMemory).toHaveBeenCalledWith("memory-1")
    expect(rejectMemory).toHaveBeenCalledWith("memory-1")
  })

  it("sends new user input through AgentCore turns", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    fireEvent.change(screen.getByLabelText("Message"), {
      target: { value: "Summarize MultiQC" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Send message" }))

    expect(sendTurn).toHaveBeenCalledWith("Summarize MultiQC")
  })

  it("updates permission mode from the composer controls", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    fireEvent.change(screen.getByRole("combobox", { name: "Tool permissions" }), {
      target: { value: "bypass" },
    })

    expect(updateSessionSettings).toHaveBeenCalledWith({
      permissionMode: "bypass",
    })
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
