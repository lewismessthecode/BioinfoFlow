import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentCoreChat } from "@/components/bioinfoflow/agent-core/agent-core-chat"
import { useAgentCore } from "@/hooks/use-agent-core"

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

describe("AgentCoreChat", () => {
  const useAgentCoreMock = vi.mocked(useAgentCore)
  const sendTurn = vi.fn()
  const setActiveSessionId = vi.fn()
  const approveAction = vi.fn()
  const rejectAction = vi.fn()
  const acceptMemory = vi.fn()
  const rejectMemory = vi.fn()

  beforeEach(() => {
    sendTurn.mockReset()
    setActiveSessionId.mockReset()
    approveAction.mockReset()
    rejectAction.mockReset()
    acceptMemory.mockReset()
    rejectMemory.mockReset()
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
      sendTurn,
      approveAction,
      rejectAction,
      acceptMemory,
      rejectMemory,
    })
  })

  it("renders AgentCore turns and event ledger", () => {
    render(<AgentCoreChat projectId="project-1" workspaceEnabled />)

    expect(screen.getByText("Session session-")).toBeInTheDocument()
    expect(screen.getByText("Check FASTQ quality")).toBeInTheDocument()
    expect(
      screen.getByText("FASTQ pairing and QC look ready for preflight."),
    ).toBeInTheDocument()
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

  it("shows a project selection state without creating a legacy chat surface", () => {
    render(<AgentCoreChat />)

    expect(screen.getByText("Select a project")).toBeInTheDocument()
    expect(screen.getByText("Choose a project from the sidebar.")).toBeInTheDocument()
    expect(useAgentCoreMock).toHaveBeenCalledWith(undefined)
  })
})
