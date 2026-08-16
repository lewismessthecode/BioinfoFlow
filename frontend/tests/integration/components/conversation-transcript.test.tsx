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
        "agentTranscript.copy": "Copy response",
        "agentTranscript.copied": "Copied response",
        "agentHistory.plan.title": "Plan",
        "agentHistory.plan.progress": `${values?.completed ?? 0}/${values?.total ?? 0} complete`,
        "agentHistory.plan.status.pending": "Pending",
        "agentHistory.plan.status.in_progress": "In progress",
        "agentHistory.plan.status.completed": "Completed",
        "agentHistory.unknown.title": "Unsupported content",
        "agentHistory.notice.title": "Agent notice",
        "agentHistory.notice.message.run_timeout_exceeded": `The run reached its ${values?.limitSeconds ?? ""}-second time limit.`,
        "agentRun.error.runtime_failed": "The Agent runtime stopped unexpectedly.",
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

    expect(screen.getByTestId("agent-transcript-content")).toHaveClass("gap-3")
    expect(screen.getByTestId("agent-transcript-content")).not.toHaveClass("gap-5")
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

  it("localizes known notices and run errors from stable codes", () => {
    renderWithProviders(
      <ConversationTranscript
        view={{
          ...planView,
          transcript: [
            {
              type: "notice",
              id: "notice-timeout",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:00.000Z",
              code: "run_timeout_exceeded",
              params: { limit_seconds: 300 },
              fallback: "Backend-owned English timeout text",
            },
            {
              type: "outcome",
              id: "run:run-1:outcome",
              runId: "run-1",
              createdAt: "2026-08-16T08:05:00.000Z",
              status: "failed",
              reason: "runtime_failed",
              error: {
                code: "runtime_failed",
                message: "Backend-owned English runtime text",
              },
            },
          ],
        }}
      />,
    )

    expect(screen.getByText("The run reached its 300-second time limit.")).toBeInTheDocument()
    expect(screen.getByText("The Agent runtime stopped unexpectedly.")).toBeInTheDocument()
    expect(screen.queryByText(/Backend-owned English/)).not.toBeInTheDocument()
  })

  it("uses a safe raw fallback only for unknown notice and run error codes", () => {
    renderWithProviders(
      <ConversationTranscript
        view={{
          ...planView,
          transcript: [
            {
              type: "notice",
              id: "notice-provider",
              runId: "run-1",
              createdAt: null,
              code: "provider_notice",
              params: {},
              fallback: "Provider maintenance is in progress.",
            },
            {
              type: "outcome",
              id: "run:run-1:outcome",
              runId: "run-1",
              createdAt: null,
              status: "failed",
              reason: "provider_failure",
              error: {
                code: "provider_failure",
                message: "Provider request failed safely.",
              },
            },
          ],
        }}
      />,
    )

    expect(screen.getByText("Provider maintenance is in progress.")).toBeInTheDocument()
    expect(screen.getByText("Provider request failed safely.")).toBeInTheDocument()
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

  it("reveals timestamps on message interaction and offers one copy action for the completed final response", async () => {
    const user = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })
    const { container } = renderWithProviders(
      <ConversationTranscript
        view={{
          ...planView,
          transcript: [
            {
              type: "message",
              id: "user-1",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:00.000Z",
              role: "user",
              text: "Inspect this workflow",
              references: [],
              streaming: false,
            },
            {
              type: "message",
              id: "assistant-part-1",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:01.000Z",
              role: "assistant",
              text: "I inspected the workflow.",
              references: [],
              streaming: false,
            },
            {
              type: "message",
              id: "assistant-final",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:02.000Z",
              role: "assistant",
              text: "The workflow is valid.\n\n```json\n{\"valid\": true}\n```",
              references: [],
              streaming: false,
            },
            {
              type: "outcome",
              id: "run-1-outcome",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:03.000Z",
              status: "completed",
              reason: null,
              error: null,
            },
          ],
        }}
      />,
    )

    const messages = container.querySelectorAll("article[data-role]")
    expect(messages).toHaveLength(3)
    for (const message of messages) {
      expect(message).toHaveClass("group/message")
      const timestamp = message.querySelector("time")
      expect(message).toHaveAttribute("aria-describedby", timestamp?.id)
      expect(timestamp).toHaveClass(
        "opacity-0",
        "group-hover/message:opacity-100",
        "group-focus-within/message:opacity-100",
      )
    }
    await user.tab()
    expect(messages[0]).toHaveFocus()
    expect(messages[0]).toHaveClass(
      "focus-visible:ring-2",
      "focus-visible:ring-ring/35",
    )
    expect(screen.getAllByRole("button", { name: "Copy response" })).toHaveLength(1)
    expect(screen.queryByRole("button", { name: "Copy code" })).toBeNull()
    expect(screen.getAllByRole("button")).toHaveLength(1)

    await user.click(screen.getByRole("button", { name: "Copy response" }))

    expect(writeText).toHaveBeenCalledOnce()
    expect(writeText).toHaveBeenCalledWith(
      "The workflow is valid.\n\n```json\n{\"valid\": true}\n```",
    )
  })

  it("keeps active Activity Groups compact and collapsed by default", () => {
    renderWithProviders(
      <ConversationTranscript
        view={{
          ...planView,
          transcript: [
            {
              type: "activity_group",
              id: "activity-run-1",
              runId: "run-1",
              createdAt: "2026-08-16T08:00:00.000Z",
              executionMode: "parallel",
              activities: [
                {
                  id: "activity-read",
                  callId: "call-read",
                  name: "read",
                  displayName: "read",
                  category: "read",
                  summary: "Read workflow.nf",
                  status: "running",
                  input: { path: "workflow.nf" },
                  output: null,
                  error: null,
                  startedAt: "2026-08-16T08:00:00.000Z",
                  completedAt: null,
                },
              ],
            },
          ],
          activeWork: {
            runId: "run-1",
            status: "running",
            phase: "tools",
            startedAt: "2026-08-16T08:00:00.000Z",
          },
        }}
      />,
    )

    const group = screen.getByTestId("agent-activity-group")
    const disclosure = group.querySelector("button")
    expect(disclosure).toHaveAttribute("aria-expanded", "false")
    expect(disclosure).toHaveClass("h-9", "py-1")
    expect(screen.queryByTestId("agent-tool-card")).not.toBeInTheDocument()
  })
})
