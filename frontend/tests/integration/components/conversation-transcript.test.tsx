import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ConversationTranscript } from "@/components/bioinfoflow/agent/conversation-transcript"
import type { ConversationViewModel } from "@/lib/agent/conversation-model/types"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentTranscript.title": "Agent transcript",
        "agentHistory.plan.title": "Plan",
        "agentHistory.plan.progress": `${values?.completed ?? 0}/${values?.total ?? 0} complete`,
        "agentHistory.plan.status.pending": "Pending",
        "agentHistory.plan.status.in_progress": "In progress",
        "agentHistory.plan.status.completed": "Completed",
        "agentHistory.unknown.title": "Unsupported content",
        "agentThinking.title": "Thinking",
        "agentThinking.show": "Show thinking",
        "agentThinking.hide": "Hide thinking",
        "agentThinking.duration": `${values?.duration ?? 0}s`,
        "agentInteraction.approval.title": "Approval required",
        "agentInteraction.approval.announcement": "Approval required",
        "agentInteraction.approval.input": "Input",
        "agentInteraction.approval.target": "Execution target",
        "agentInteraction.approval.effects": "Effects",
        "agentInteraction.approval.reasons": "Reasons",
        "agentInteraction.approval.resources": "Resources",
        "agentInteraction.approval.reject": "Reject",
        "agentInteraction.approval.approve": "Approve",
        "agentInteraction.status.pending": "Pending",
        "agentInteraction.status.expired": "Expired",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const planView: ConversationViewModel = {
  protocolVersion: 1,
  conversation: {
    id: "session-1",
    title: null,
    status: "active",
    workspaceId: "workspace-1",
    projectId: null,
  },
  composer: {
    placement: "docked",
    canSend: true,
    settings: {
      model: { provider: "openai", model: "gpt-5.6", displayName: "GPT-5.6" },
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
  transcript: [
    {
      type: "plan",
      id: "plan-entry-1",
      runId: "run-1",
      createdAt: "2026-08-16T08:00:00.000Z",
      planId: "plan-1",
      revision: 2,
      title: "Investigate the workflow",
      items: [
        { id: "step-1", text: "Inspect logs", status: "completed" },
        { id: "step-2", text: "Verify outputs", status: "in_progress" },
      ],
      updatedAt: "2026-08-16T08:00:01.000Z",
    },
  ],
  activeWork: null,
}

describe("ConversationTranscript", () => {
  it("renders a stable plan block with the existing Agent plan presentation", () => {
    renderWithProviders(<ConversationTranscript view={planView} />)

    expect(screen.getByText("Investigate the workflow")).toBeInTheDocument()
    expect(screen.getByText("1/2 complete")).toBeInTheDocument()
    expect(screen.getByText("Inspect logs")).toBeInTheDocument()
    expect(screen.getByText("Verify outputs")).toBeInTheDocument()
    expect(screen.queryByTestId("agent-unknown-transcript-block")).toBeNull()
  })

  it("shows completed reasoning duration from the stable transcript block", () => {
    renderWithProviders(
      <ConversationTranscript
        view={{
          ...planView,
          transcript: [
            {
              type: "reasoning",
              id: "reasoning-1",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:00.000Z",
              text: "Inspect the workflow first.",
              streaming: false,
              provider: "openai",
              model: "gpt-5.6",
              sourceField: "reasoning_trace",
              truncated: false,
              startedAt: "2026-08-16T08:00:00.000Z",
              completedAt: "2026-08-16T08:00:01.500Z",
              durationMs: 1500,
            },
          ],
        }}
      />,
    )

    expect(screen.getByTestId("agent-thinking")).toHaveTextContent("1.5s")
  })

  it("only enables the current run interaction and marks historical approvals expired", async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    const approval = {
      type: "approval" as const,
      callId: "tool-call-reused",
      toolName: "bash",
      summary: "Run the requested command",
      inputPreview: "rm generated.tmp",
      allowedResponses: ["approve", "reject"] as const,
      risk: {
        level: "high",
        effects: ["Deletes a file"],
        reasons: ["Destructive command"],
        affectedResources: ["generated.tmp"],
      },
      target: {
        environmentId: "ssh:cluster-a",
        displayName: "Cluster A",
        kind: "ssh" as const,
        host: "cluster-a.example.org",
      },
    }
    renderWithProviders(
      <ConversationTranscript
        view={{
          ...planView,
          transcript: [
            {
              type: "interaction",
              id: "approval-old",
              runId: "run-old",
              createdAt: "2026-08-16T08:00:00.000Z",
              interactionId: "run-old:tool-call-reused",
              status: "pending",
              request: approval,
              response: null,
            },
            {
              type: "interaction",
              id: "approval-current-durable-history",
              runId: "run-current",
              createdAt: "2026-08-16T08:00:59.000Z",
              interactionId: "run-current:tool-call-reused",
              status: "pending",
              request: approval,
              response: null,
            },
            {
              type: "interaction",
              id: "approval-current",
              runId: "run-current",
              createdAt: "2026-08-16T08:01:00.000Z",
              interactionId: "run-current:tool-call-reused",
              status: "pending",
              request: approval,
              response: null,
            },
          ],
          activeWork: {
            runId: "run-current",
            status: "waiting_user",
            phase: "interaction",
            startedAt: "2026-08-16T08:01:00.000Z",
          },
        }}
        onRespond={onRespond}
      />,
    )

    const cards = screen.getAllByTestId("agent-interaction-card")
    expect(cards[0]).toHaveTextContent("Expired")
    expect(cards[0]).toHaveTextContent("Cluster A")
    expect(cards[0]).toHaveTextContent("cluster-a.example.org")
    expect(cards[0].querySelectorAll("button")).toHaveLength(0)
    expect(cards[1]).toHaveTextContent("Expired")
    expect(cards[1].querySelectorAll("button")).toHaveLength(0)
    expect(cards[2]).toHaveTextContent("Pending")

    await user.click(screen.getAllByRole("button", { name: "Approve" })[0])

    expect(onRespond).toHaveBeenCalledWith(
      "run-current:tool-call-reused",
      { type: "approval", approved: true },
    )
  })
})
