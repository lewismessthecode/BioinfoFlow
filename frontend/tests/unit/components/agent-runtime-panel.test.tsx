import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { PendingDecisionCards } from "@/components/bioinfoflow/agent-runtime/pending-decision-cards"
import { ProgressTab } from "@/components/bioinfoflow/agent-runtime/progress-tab"
import type { AgentRuntimeArtifact, AgentRuntimeEvent } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

function waitingEvent(payload: Record<string, unknown>): AgentRuntimeEvent {
  return {
    id: `event-${payload.action_id}`,
    session_id: "session-1",
    turn_id: "turn-1",
    seq: 1,
    type: "action.waiting_decision",
    payload,
    visibility: "user",
    schema_version: 1,
    created_at: "2026-06-09T00:00:00Z",
    updated_at: "2026-06-09T00:00:00Z",
  }
}

function artifact(overrides: Partial<AgentRuntimeArtifact>): AgentRuntimeArtifact {
  return {
    id: "artifact-1",
    session_id: "session-1",
    turn_id: "turn-1",
    action_id: "action-1",
    type: "todo_list",
    title: "Tasks",
    summary: "1/2 completed",
    payload: null,
    file_path: null,
    resource_ref: null,
    created_at: "2026-06-09T00:00:00Z",
    updated_at: "2026-06-09T00:00:00Z",
    ...overrides,
  }
}

describe("ProgressTab", () => {
  it("renders the latest todo checklist", () => {
    render(
      <ProgressTab
        artifacts={[
          artifact({
            payload: {
              todos: [
                { content: "Read the code", status: "completed" },
                { content: "Make the change", status: "in_progress", activeForm: "Editing" },
              ],
            },
          }),
        ]}
      />,
    )
    expect(screen.getByTestId("todo-checklist")).toBeInTheDocument()
    expect(screen.getByText("Read the code")).toBeInTheDocument()
    // in_progress uses activeForm
    expect(screen.getByText("Editing")).toBeInTheDocument()
  })
})

describe("PendingDecisionCards", () => {
  it("submits an ask_user answer", () => {
    const onDecision = vi.fn()
    render(
      <PendingDecisionCards
        events={[
          waitingEvent({
            action_id: "a1",
            name: "ask_user",
            interaction: {
              kind: "user_input",
              questions: [
                {
                  question: "Which DB?",
                  header: "DB",
                  options: [
                    { label: "Postgres", description: "Relational" },
                    { label: "SQLite", description: "Embedded" },
                  ],
                },
              ],
            },
          }),
        ]}
        onDecision={onDecision}
      />,
    )
    expect(screen.getByTestId("ask-user-card")).toBeInTheDocument()
    fireEvent.click(screen.getByText("SQLite"))
    fireEvent.click(screen.getByText("ask.submit"))
    expect(onDecision).toHaveBeenCalledWith("a1", "answer", {
      answer: { DB: "SQLite" },
    })
  })

  it("approves a plan", () => {
    const onDecision = vi.fn()
    render(
      <PendingDecisionCards
        events={[
          waitingEvent({
            action_id: "a2",
            name: "exit_plan_mode",
            interaction: { kind: "plan_approval", plan: "1. step one" },
          }),
        ]}
        onDecision={onDecision}
      />,
    )
    expect(screen.getByTestId("plan-approval-card")).toBeInTheDocument()
    expect(screen.getByText("1. step one")).toBeInTheDocument()
    fireEvent.click(screen.getByText("plan.approveAndAct"))
    expect(onDecision).toHaveBeenCalledWith("a2", "approve")
  })

  it("renders a generic approval card with name and preview", () => {
    const onDecision = vi.fn()
    render(
      <PendingDecisionCards
        events={[
          waitingEvent({
            action_id: "a3",
            name: "bash",
            risk_level: "act_high",
            input_preview: "rm build/",
          }),
        ]}
        onDecision={onDecision}
      />,
    )
    expect(screen.getByText("bash")).toBeInTheDocument()
    expect(screen.getByText("rm build/")).toBeInTheDocument()
    fireEvent.click(screen.getByText("approve"))
    expect(onDecision).toHaveBeenCalledWith("a3", "approve")
    fireEvent.click(screen.getByText("reject"))
    expect(onDecision).toHaveBeenCalledWith("a3", "reject")
  })
})
