import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentSideDrawer } from "@/components/bioinfoflow/agent-runtime/agent-side-drawer"
import { ArtifactPreviewDrawer } from "@/components/bioinfoflow/agent-runtime/artifact-preview-drawer"
import { ArtifactViewer } from "@/components/bioinfoflow/agent-runtime/artifact-viewers"
import { BrowserTab } from "@/components/bioinfoflow/agent-runtime/browser-tab"
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
  it("keeps routine command artifacts out of the preview tab", () => {
    render(
      <ArtifactPreviewDrawer
        artifacts={[
          artifact({
            id: "command-1",
            type: "command",
            title: "ls output",
            payload: { command: "ls", stdout: "report.md", stderr: "" },
          }),
          artifact({
            id: "run-1",
            type: "run",
            title: "Run record",
            resource_ref: { url: "/api/v1/runs/run-1" },
            payload: { run: { id: "run-1" } },
          }),
          artifact({
            id: "file-1",
            type: "file",
            title: "report.md",
            summary: null,
            file_path: "/workspace/report.md",
            payload: { content: "QC passed" },
          }),
        ]}
      />,
    )

    const drawer = screen.getByTestId("artifact-preview-drawer")
    expect(within(drawer).getByRole("button", { name: /report.md/ })).toBeInTheDocument()
    expect(screen.getByText("/workspace/report.md")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /ls output/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Run record/ })).not.toBeInTheDocument()
    expect(screen.queryByText("artifacts.toolLogs")).not.toBeInTheDocument()
  })
})

describe("ArtifactViewer", () => {
  it("renders markdown file artifacts through the markdown renderer", () => {
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "markdown-1",
          type: "file",
          title: "report.md",
          payload: { path: "/workspace/report.md", content: "# QC Report\n\n| sample | status |\n| --- | --- |\n| A | pass |" },
        })}
      />,
    )

    expect(screen.getByRole("heading", { name: "QC Report" })).toBeInTheDocument()
    expect(screen.getByRole("table")).toHaveTextContent("sample")
  })

  it("renders html artifacts in a sandboxed frame", () => {
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "html-1",
          type: "html",
          title: "report.html",
          payload: { content: "<h1>Interactive report</h1>" },
        })}
      />,
    )

    const frame = screen.getByTitle("report.html")
    expect(frame).toHaveAttribute("sandbox", "")
    expect(frame).toHaveAttribute("srcdoc", "<h1>Interactive report</h1>")
  })

  it("renders csv artifacts as a table", () => {
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "sheet-1",
          type: "file",
          title: "metrics.csv",
          payload: { path: "/workspace/metrics.csv", content: "sample,reads\nA,42" },
        })}
      />,
    )

    expect(screen.getByRole("table")).toHaveTextContent("reads")
    expect(screen.getByRole("table")).toHaveTextContent("42")
  })

  it("renders pdf artifacts with an embedded viewer when a URL is available", () => {
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "pdf-1",
          type: "pdf",
          title: "summary.pdf",
          payload: { url: "/api/v1/agent/artifacts/pdf-1/raw" },
        })}
      />,
    )

    expect(screen.getByTitle("summary.pdf")).toHaveAttribute(
      "src",
      "/api/v1/agent/artifacts/pdf-1/raw",
    )
    expect(screen.queryByRole("button", { name: "artifacts.copy" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "artifacts.download" })).not.toBeInTheDocument()
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

describe("BrowserTab", () => {
  it("starts blank instead of loading the current Bioinfoflow route", () => {
    render(<BrowserTab />)

    const input = screen.getByPlaceholderText("browser.urlPlaceholder")
    expect(input).toHaveValue("")
    expect(screen.getByText("browser.empty")).toBeInTheDocument()
    expect(screen.queryByTitle("browser.title")).not.toBeInTheDocument()
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

  it("submits a custom ask_user answer", () => {
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
    fireEvent.change(screen.getByPlaceholderText("ask.customPlaceholder"), {
      target: { value: "DuckDB with parquet staging" },
    })
    fireEvent.click(screen.getByText("ask.submit"))
    expect(onDecision).toHaveBeenCalledWith("a1", "answer", {
      answer: { DB: "DuckDB with parquet staging" },
    })
  })

  it("keeps custom text when adding a multi-select ask_user option", () => {
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
                  question: "Which checks?",
                  header: "Checks",
                  multiSelect: true,
                  options: [
                    { label: "FastQC", description: "Read-level QC" },
                    { label: "MultiQC", description: "Aggregate reports" },
                  ],
                },
              ],
            },
          }),
        ]}
        onDecision={onDecision}
      />,
    )
    fireEvent.change(screen.getByPlaceholderText("ask.customPlaceholder"), {
      target: { value: "Adapter trimming summary" },
    })
    fireEvent.click(screen.getByText("FastQC"))
    fireEvent.click(screen.getByText("ask.submit"))
    expect(onDecision).toHaveBeenCalledWith("a1", "answer", {
      answer: { Checks: ["FastQC", "Adapter trimming summary"] },
    })
  })

  it("labels the custom input and reject action explicitly", () => {
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
                  options: [{ label: "SQLite", description: "Embedded" }],
                },
              ],
            },
          }),
        ]}
        onDecision={vi.fn()}
      />,
    )

    expect(screen.getByText("ask.customLabel")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "ask.rejectQuestion" })).toBeInTheDocument()
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
