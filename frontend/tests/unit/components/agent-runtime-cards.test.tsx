import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { InlineApprovalCard } from "@/components/bioinfoflow/agent-runtime/inline-approval-card"
import { PendingDecisionCards } from "@/components/bioinfoflow/agent-runtime/pending-decision-cards"
import { getActionDecisionCards } from "@/components/bioinfoflow/agent-runtime/pending-actions"
import type {
  AgentRuntimeDecisionView,
  AgentRuntimeEvent,
} from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const labels: Record<string, string> = {
      approve: "Approve",
      reject: "Reject",
      "sidecar.needsDecision": "Needs your decision",
      "plan.reviewTitle": "Review the plan",
      "plan.approveAndAct": "Approve and act",
      "plan.keepPlanning": "Keep planning",
      "ask.title": "Question",
      "ask.recommended": "Recommended",
      "ask.answerLabel": "Answer",
      "ask.customLabel": "Other",
      "ask.customPlaceholder": "Type an answer",
      "ask.rejectQuestion": "Reject question",
      "ask.submit": "Submit answer",
      "decision.submitting": "Submitting decision...",
      "decision.failed": `Could not submit decision: ${values?.error ?? ""}`,
      "decision.retry": "Retry decision",
      "approval.remoteTarget": `Remote target: ${values?.target ?? ""}`,
    }
    return labels[key] ?? key
  },
}))

const baseDecision: AgentRuntimeDecisionView = {
  actionId: "action-1",
  name: "remote.exec",
  riskLevel: "act_high",
  inputPreview: "cat /data/input.txt",
  interaction: null,
  state: "pending",
  turnId: "turn-1",
  seqStart: 1,
  seqEnd: 1,
  scrollTargetId: "agent-decision-action-1",
}

describe("agent decision cards", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("suppresses duplicate inline decisions and disables both actions while pending", async () => {
    const request = deferred<void>()
    const onDecision = vi.fn(() => request.promise)
    render(<InlineApprovalCard decision={baseDecision} onDecision={onDecision} />)

    fireEvent.click(screen.getByRole("button", { name: "Approve" }))
    fireEvent.click(screen.getByRole("button", { name: "Approve" }))

    expect(onDecision).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled()
    expect(screen.getByRole("status")).toHaveTextContent("Submitting decision...")

    request.resolve()
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled())
  })

  it("keeps an inline decision failure on its card and retries the same decision", async () => {
    const onDecision = vi
      .fn()
      .mockRejectedValueOnce(new Error("Action already claimed"))
      .mockResolvedValueOnce(undefined)
    render(<InlineApprovalCard decision={baseDecision} onDecision={onDecision} />)

    fireEvent.click(screen.getByRole("button", { name: "Reject" }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not submit decision: Action already claimed",
    )
    fireEvent.click(screen.getByRole("button", { name: "Retry decision" }))

    await waitFor(() => expect(onDecision).toHaveBeenCalledTimes(2))
    expect(onDecision).toHaveBeenLastCalledWith("action-1", "reject")
  })

  it("protects plan approval from double submission", () => {
    const request = deferred<void>()
    const onDecision = vi.fn(() => request.promise)
    render(
      <InlineApprovalCard
        decision={{
          ...baseDecision,
          name: "exit_plan_mode",
          interaction: { kind: "plan_approval", plan: "1. Validate inputs" },
        }}
        onDecision={onDecision}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Approve and act" }))
    fireEvent.click(screen.getByRole("button", { name: "Approve and act" }))

    expect(onDecision).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "Keep planning" })).toBeDisabled()
  })

  it("protects question answers from duplicate submission and supports retry", async () => {
    const onDecision = vi
      .fn()
      .mockRejectedValueOnce(new Error("Connection lost"))
      .mockResolvedValueOnce(undefined)
    render(
      <InlineApprovalCard
        decision={{
          ...baseDecision,
          name: "ask_user",
          interaction: {
            kind: "user_input",
            questions: [
              {
                header: "Scope",
                question: "Which scope?",
                options: [{ label: "Current session" }],
              },
            ],
          },
        }}
        onDecision={onDecision}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /Current session/ }))
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }))
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }))

    expect(onDecision).toHaveBeenCalledTimes(1)
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not submit decision: Connection lost",
    )
    fireEvent.click(screen.getByRole("button", { name: "Retry decision" }))
    await waitFor(() => expect(onDecision).toHaveBeenCalledTimes(2))
  })

  it("keeps submission state independent across pending cards", () => {
    const request = deferred<void>()
    const onDecision = vi.fn((actionId: string) =>
      actionId === "action-1" ? request.promise : Promise.resolve(),
    )
    render(
      <PendingDecisionCards
        events={[waitingEvent("action-1", 1), waitingEvent("action-2", 2)]}
        onDecision={onDecision}
      />,
    )

    const cards = screen.getAllByTestId("pending-approval-card")
    fireEvent.click(within(cards[0]).getByRole("button", { name: "Approve" }))

    expect(within(cards[0]).getByRole("button", { name: "Approve" })).toBeDisabled()
    expect(within(cards[1]).getByRole("button", { name: "Approve" })).toBeEnabled()
  })

  it("renders the remote target persisted for the matching action assessment", () => {
    const events: AgentRuntimeEvent[] = [
      {
        ...waitingEvent("action-1", 2),
        id: "risk-1",
        seq: 1,
        type: "action.risk_assessed",
        payload: {
          action_id: "action-1",
          risk_level: "act_high",
          target: {
            kind: "remote_ssh",
            trust_domain: "sz01.example.org",
            identity: "bioflow",
            connection_id: "connection-sz01",
          },
        },
      },
      waitingEvent("action-1", 2),
    ]
    const [decision] = getActionDecisionCards(events)

    render(<InlineApprovalCard decision={decision} onDecision={vi.fn()} />)

    expect(screen.getByText("Remote target: bioflow@sz01.example.org")).toBeInTheDocument()
  })
})

function waitingEvent(actionId: string, seq: number): AgentRuntimeEvent {
  return {
    id: `event-${actionId}-${seq}`,
    session_id: "session-1",
    turn_id: "turn-1",
    seq,
    type: "action.waiting_decision",
    payload: {
      action_id: actionId,
      name: "remote.exec",
      risk_level: "act_high",
      input_preview: "hostname",
    },
    visibility: "user",
    schema_version: 1,
    created_at: "2026-07-13T00:00:00Z",
    updated_at: "2026-07-13T00:00:00Z",
  }
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}
