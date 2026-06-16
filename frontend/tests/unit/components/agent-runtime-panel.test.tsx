import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentSideDrawer } from "@/components/bioinfoflow/agent-runtime/agent-side-drawer"
import { ArtifactPreviewDrawer } from "@/components/bioinfoflow/agent-runtime/artifact-preview-drawer"
import { resolveSameOriginBrowserUrl } from "@/components/bioinfoflow/agent-runtime/browser-tab"
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

describe("ArtifactPreviewDrawer", () => {
  it("opens command artifacts with full output", () => {
    render(
      <ArtifactPreviewDrawer
        artifacts={[
          artifact({
            id: "command-1",
            type: "command",
            title: "ls output",
            payload: { command: "ls", stdout: "report.md", stderr: "" },
          }),
          artifact({ id: "file-1", type: "file", title: "report.md", payload: { content: "QC passed" } }),
        ]}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /ls output/ }))

    expect(screen.getByText("$ ls")).toBeInTheDocument()
    expect(screen.getByText("report.md")).toBeInTheDocument()
  })
})

describe("AgentSideDrawer", () => {
  it("keeps environment information out of the right drawer", () => {
    render(
      <AgentSideDrawer
        projectId="project-1"
        sessionId={null}
        events={[
          {
            id: "event-change",
            session_id: "session-1",
            turn_id: "turn-1",
            seq: 1,
            type: "action.completed",
            payload: {
              action_id: "a1",
              name: "files__write",
              result: {
                path: "/workspace/project-1/workflow.nf",
                additions: 12,
                deletions: 3,
              },
            },
            visibility: "user",
            schema_version: 1,
            created_at: "2026-06-09T00:00:00Z",
            updated_at: "2026-06-09T00:00:00Z",
          },
        ]}
        onClose={vi.fn()}
      />,
    )

    const drawer = screen.getByTestId("artifact-panel")
    expect(within(drawer).queryByTestId("agent-environment-card")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "tabs.environment" })).not.toBeInTheDocument()
  })

  it("renders pending decision jump as an interactive button", () => {
    const target = document.createElement("div")
    target.id = "agent-decision-a1"
    target.scrollIntoView = vi.fn()
    document.body.appendChild(target)

    render(
      <AgentSideDrawer
        events={[waitingEvent({ action_id: "a1", name: "bash" })]}
        onClose={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "approval.jumpToDecision" }))
    expect(target.scrollIntoView).toHaveBeenCalledWith({
      block: "center",
      behavior: "smooth",
    })
    target.remove()
  })
})

describe("resolveSameOriginBrowserUrl", () => {
  it("rejects lookalike cross-origin iframe URLs", () => {
    expect(
      resolveSameOriginBrowserUrl(
        "https://bioinfoflow.example.evil.test/app",
        "https://bioinfoflow.example",
      ),
    ).toBe("https://bioinfoflow.example/")
  })

  it("normalizes same-origin absolute and relative URLs", () => {
    expect(
      resolveSameOriginBrowserUrl(
        "https://bioinfoflow.example/agent?tab=browser#panel",
        "https://bioinfoflow.example",
      ),
    ).toBe("https://bioinfoflow.example/agent?tab=browser#panel")
    expect(resolveSameOriginBrowserUrl("/runs", "https://bioinfoflow.example")).toBe(
      "https://bioinfoflow.example/runs",
    )
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
