import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentCoreTurnBlock } from "@/components/bioinfoflow/agent-core/agent-core-turn-block"
import type {
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreTurn,
} from "@/lib/agent-core"

vi.mock("next-intl", () => ({
  useTranslations: () => {
    const copy: Record<string, string> = {
      acceptMemory: "Accept memory",
      actionApproval: "Approval required",
      actionTimeline: "Action timeline",
      approveAction: "Approve action",
      artifactPanel: "Artifacts",
      auditToggle: "View events",
      clarificationRequested: "Clarification requested",
      clarificationResolved: "Resolved",
      eventLedger: "Event ledger",
      memoryProposals: "Memory proposals",
      noFinalText: "No final response was recorded for this turn.",
      reactionCopy: "Copy response",
      reactionDislike: "Dislike response",
      reactionLike: "Like response",
      reactionMore: "More response actions",
      reactionRegenerate: "Regenerate response",
      rejectAction: "Reject action",
      rejectMemory: "Reject memory",
    }
    return (key: string) => copy[key] ?? key
  },
}))

const timestamp = "2026-06-04T00:00:00Z"

function turn(overrides: Partial<AgentCoreTurn> = {}): AgentCoreTurn {
  return {
    id: "turn-1",
    session_id: "session-1",
    project_id: "project-1",
    workspace_id: "workspace-1",
    user_id: "user-1",
    input_text: "Check FASTQ quality",
    status: "completed",
    final_text: "FASTQ pairing and QC look ready for preflight.",
    created_at: timestamp,
    updated_at: timestamp,
    ...overrides,
  }
}

function event(
  id: string,
  seq: number,
  type: string,
  payload: Record<string, unknown> = {},
): AgentCoreEvent {
  return {
    id,
    session_id: "session-1",
    turn_id: "turn-1",
    seq,
    type,
    payload,
    visibility: "user",
    schema_version: 1,
    created_at: timestamp,
    updated_at: timestamp,
  }
}

function renderTurn({
  currentTurn = turn(),
  events = [],
  artifacts = [],
  memories = [],
  onApproveAction = vi.fn(),
  onRejectAction = vi.fn(),
  onAcceptMemory = vi.fn(),
  onRejectMemory = vi.fn(),
}: {
  currentTurn?: AgentCoreTurn
  events?: AgentCoreEvent[]
  artifacts?: AgentCoreArtifact[]
  memories?: AgentCoreMemory[]
  onApproveAction?: (actionId: string) => void
  onRejectAction?: (actionId: string) => void
  onAcceptMemory?: (memoryId: string) => void
  onRejectMemory?: (memoryId: string) => void
} = {}) {
  render(
    <AgentCoreTurnBlock
      turn={currentTurn}
      events={events}
      artifacts={artifacts}
      memories={memories}
      onApproveAction={onApproveAction}
      onRejectAction={onRejectAction}
      onAcceptMemory={onAcceptMemory}
      onRejectMemory={onRejectMemory}
    />,
  )
}

describe("AgentCoreTurnBlock", () => {
  it("renders turn input and final text with assistant actions", () => {
    renderTurn()

    expect(screen.getByText("Check FASTQ quality")).toBeInTheDocument()
    expect(
      screen.getByText("FASTQ pairing and QC look ready for preflight."),
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Like response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Dislike response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Regenerate response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Copy response" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "More response actions" })).toBeInTheDocument()
  })

  it("renders a turn error instead of the empty-response fallback", () => {
    renderTurn({
      currentTurn: turn({
        input_text: "Run alignment",
        status: "failed",
        final_text: null,
        error_code: "model_request_failed",
        error_message: "Provider timed out",
      }),
    })

    expect(screen.getByText("Provider timed out")).toBeInTheDocument()
    expect(
      screen.queryByText("No final response was recorded for this turn."),
    ).not.toBeInTheDocument()
  })

  it("renders requested and resolved user questions", () => {
    renderTurn({
      events: [
        event("event-1", 1, "user_input.requested", {
          request_id: "question-1",
          question: "Which reference genome should I use?",
          options: ["hg19", { label: "hg38" }],
          reason: "Reference genome affects alignment and annotation.",
        }),
        event("event-2", 2, "user_input.resolved", {
          request_id: "question-1",
          answer: "hg38",
        }),
      ],
    })

    expect(screen.getByText("Clarification requested")).toBeInTheDocument()
    expect(screen.getByText("Which reference genome should I use?")).toBeInTheDocument()
    expect(
      screen.getByText("Reference genome affects alignment and annotation."),
    ).toBeInTheDocument()
    expect(screen.getByText("hg19")).toBeInTheDocument()
    expect(screen.getAllByText("hg38")).toHaveLength(2)
    expect(screen.getByText("Resolved")).toBeInTheDocument()
  })

  it("renders the action timeline and dispatches approval decisions", () => {
    const onApproveAction = vi.fn()
    const onRejectAction = vi.fn()
    renderTurn({
      events: [
        event("event-1", 1, "action.requested", {
          action_id: "action-1",
          name: "execution.shell",
          kind: "tool",
          risk_level: "act_high",
          input_preview: "Run command: ls results",
        }),
        event("event-2", 2, "action.waiting_decision", {
          action_id: "action-1",
          name: "execution.shell",
        }),
      ],
      onApproveAction,
      onRejectAction,
    })

    expect(screen.getByText("Action timeline")).toBeInTheDocument()
    expect(screen.getByText("Approval required")).toBeInTheDocument()
    expect(screen.getByText("execution.shell")).toBeInTheDocument()
    expect(screen.getByText("act_high")).toBeInTheDocument()
    expect(screen.getByText("Run command: ls results")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Approve action" }))
    fireEvent.click(screen.getByRole("button", { name: "Reject action" }))

    expect(onApproveAction).toHaveBeenCalledWith("action-1")
    expect(onRejectAction).toHaveBeenCalledWith("action-1")
  })

  it("renders artifacts and memories and dispatches memory decisions", () => {
    const onAcceptMemory = vi.fn()
    const onRejectMemory = vi.fn()
    renderTurn({
      artifacts: [
        {
          id: "artifact-1",
          session_id: "session-1",
          turn_id: "turn-1",
          action_id: "action-1",
          type: "log_summary",
          title: "execution.shell output",
          summary: "Command exited with code 0.",
          created_at: timestamp,
          updated_at: timestamp,
        },
      ],
      memories: [
        {
          id: "memory-1",
          workspace_id: "workspace-1",
          project_id: "project-1",
          session_id: "session-1",
          scope: "project",
          type: "project_convention",
          content: { reference_genome: "hg38" },
          confidence: 91,
          status: "proposed",
          created_at: timestamp,
          updated_at: timestamp,
        },
      ],
      onAcceptMemory,
      onRejectMemory,
    })

    expect(screen.getByText("Artifacts")).toBeInTheDocument()
    expect(screen.getByText("execution.shell output")).toBeInTheDocument()
    expect(screen.getByText("Command exited with code 0.")).toBeInTheDocument()
    expect(screen.getByText("Memory proposals")).toBeInTheDocument()
    expect(screen.getByText("project_convention")).toBeInTheDocument()
    expect(screen.getByText(/reference_genome/)).toBeInTheDocument()
    expect(screen.getByText("91%")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Accept memory" }))
    fireEvent.click(screen.getByRole("button", { name: "Reject memory" }))

    expect(onAcceptMemory).toHaveBeenCalledWith("memory-1")
    expect(onRejectMemory).toHaveBeenCalledWith("memory-1")
  })

  it("keeps the event ledger collapsed until requested", () => {
    renderTurn({
      events: [
        event("event-1", 1, "turn.created", {
          input_text: "Check FASTQ quality",
        }),
        event("event-2", 2, "assistant.text.completed", {
          text: "FASTQ pairing and QC look ready for preflight.",
        }),
      ],
    })

    expect(screen.getByText("View events")).toBeInTheDocument()
    expect(screen.queryByText("Event ledger")).not.toBeInTheDocument()

    fireEvent.click(screen.getByText("View events"))

    expect(screen.getByText("Event ledger")).toBeInTheDocument()
    expect(screen.getByText("turn.created")).toBeInTheDocument()
    expect(screen.getByText("assistant.text.completed")).toBeInTheDocument()
  })
})
