import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentSideDrawer } from "@/components/bioinfoflow/agent-runtime/agent-side-drawer"
import { AgentTabbedPanel } from "@/components/bioinfoflow/agent-runtime/agent-tabbed-panel"
import { ArtifactPreviewDrawer } from "@/components/bioinfoflow/agent-runtime/artifact-preview-drawer"
import { ArtifactViewer } from "@/components/bioinfoflow/agent-runtime/artifact-viewers"
import { BrowserTab, resolveBrowserUrl } from "@/components/bioinfoflow/agent-runtime/browser-tab"
import { PendingDecisionCards } from "@/components/bioinfoflow/agent-runtime/pending-decision-cards"
import { ProgressTab } from "@/components/bioinfoflow/agent-runtime/progress-tab"
import type { AgentRuntimeArtifact, AgentRuntimeEvent } from "@/lib/agent-runtime"

const listAgentRuntimeSessionArtifactsMock = vi.hoisted(() => vi.fn())

vi.mock("@/lib/agent-runtime", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/agent-runtime")>()
  return {
    ...actual,
    listAgentRuntimeSessionArtifacts: listAgentRuntimeSessionArtifactsMock,
  }
})

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

beforeEach(() => {
  vi.restoreAllMocks()
  listAgentRuntimeSessionArtifactsMock.mockReset()
})

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
  it("announces the artifact loading skeleton as status", () => {
    render(<ArtifactPreviewDrawer artifacts={[]} status="loading" />)

    expect(screen.getByRole("status", { name: "artifacts.loading" })).toBeInTheDocument()
  })

  it("announces artifact loading errors", () => {
    render(<ArtifactPreviewDrawer artifacts={[]} status="error" error="Network down" />)

    expect(screen.getByRole("alert", { name: "artifacts.loadFailed" })).toHaveTextContent(
      "Network down",
    )
  })

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

  it("keeps selected artifact previews on a full-height layout chain", async () => {
    render(
      <ArtifactPreviewDrawer
        artifacts={[
          artifact({
            id: "file-1",
            type: "file",
            title: "report.md",
            summary: null,
            file_path: "/workspace/report.md",
            payload: { content: "# QC report" },
          }),
        ]}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /report.md/ }))

    expect(screen.getByRole("heading", { name: "QC report" })).toBeInTheDocument()
    expect(screen.getByTestId("artifact-preview-drawer")).toHaveClass("h-full")
    expect(screen.getByTestId("universal-file-renderer")).toHaveClass("h-full")
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "artifacts.back" })).toHaveFocus()
    })
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
    const pdfUrl = "/api/v1/agent/fs/download?path=%2Fworkspace%2Fsummary.pdf&inline=true"
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "pdf-1",
          type: "pdf",
          title: "summary.pdf",
          payload: { url: pdfUrl },
        })}
      />,
    )

    expect(screen.getByTitle("summary.pdf")).toHaveAttribute(
      "src",
      pdfUrl,
    )
    expect(screen.queryByRole("button", { name: "artifacts.copy" })).not.toBeInTheDocument()
    expect(screen.getByRole("link", { name: "artifacts.open" })).toHaveAttribute(
      "href",
      pdfUrl,
    )
    expect(screen.getByRole("link", { name: "artifacts.download" })).toHaveAttribute(
      "href",
      pdfUrl,
    )
  })

  it("opens file-backed artifacts without showing empty copy actions", () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}) as Promise<Response>)

    render(
      <ArtifactViewer
        artifact={artifact({
          id: "custom-1",
          type: "custom_format",
          title: "result.custom",
          file_path: "/workspace/result.custom",
          payload: null,
        })}
      />,
    )

    expect(screen.getByTestId("artifact-file-viewer")).toBeInTheDocument()
    expect(screen.getByText("/workspace/result.custom")).toBeInTheDocument()
    expect(screen.getByText("renderer.textLoading")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "artifacts.open" })).toHaveAttribute(
      "href",
      expect.stringContaining("inline=true"),
    )
    expect(screen.getByRole("link", { name: "artifacts.download" })).toHaveAttribute(
      "href",
      expect.stringContaining("/agent/fs/download"),
    )
    expect(screen.queryByRole("button", { name: "artifacts.copy" })).not.toBeInTheDocument()
  })

  it("ignores unsafe artifact resource URLs", () => {
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "unsafe-pdf",
          type: "pdf",
          title: "summary.pdf",
          payload: { url: "javascript:alert(1)" },
        })}
      />,
    )

    expect(screen.queryByTitle("summary.pdf")).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "artifacts.open" })).not.toBeInTheDocument()
    expect(screen.getByText("renderer.noRenderableSource")).toBeInTheDocument()
  })

  it("rejects non-download API artifact resource URLs", () => {
    render(
      <ArtifactViewer
        artifact={artifact({
          id: "api-pdf",
          type: "pdf",
          title: "summary.pdf",
          payload: { url: "/api/v1/users/me" },
        })}
      />,
    )

    expect(screen.queryByTitle("summary.pdf")).not.toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "artifacts.open" })).not.toBeInTheDocument()
    expect(screen.getByText("renderer.noRenderableSource")).toBeInTheDocument()
  })
})

describe("AgentTabbedPanel", () => {
  it("uses tab semantics for the right-side artifact workspace", () => {
    const onActiveTabChange = vi.fn()
    render(
      <AgentTabbedPanel
        projectId="project-1"
        sessionId={null}
        events={[]}
        activeTab="preview"
        onActiveTabChange={onActiveTabChange}
        browserInput=""
        browserSrc=""
        onBrowserInputChange={vi.fn()}
        onBrowserSrcChange={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByRole("tablist", { name: "sidecar.title" })).toBeInTheDocument()
    expect(screen.getByText("tabs.artifacts")).toBeInTheDocument()
    expect(screen.getByText("tabs.files")).toBeInTheDocument()
    expect(screen.getByText("tabs.browser")).toBeInTheDocument()
    expect(screen.queryByText("artifacts.title")).not.toBeInTheDocument()
    expect(screen.queryByText("sidecar.title")).not.toBeInTheDocument()
    expect(screen.queryByText("artifacts.count")).not.toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "tabs.artifacts" })).toHaveAttribute(
      "aria-selected",
      "true",
    )
    expect(screen.getByRole("tab", { name: "tabs.files" })).toHaveAttribute(
      "aria-selected",
      "false",
    )
    fireEvent.keyDown(screen.getByRole("tab", { name: "tabs.artifacts" }), {
      key: "ArrowRight",
    })
    expect(onActiveTabChange).toHaveBeenCalledWith("files")
  })

  it("labels the artifact panel as loading instead of reporting zero artifacts", () => {
    listAgentRuntimeSessionArtifactsMock.mockReturnValue(new Promise(() => {}))

    render(
      <AgentTabbedPanel
        projectId="project-1"
        sessionId="session-1"
        events={[]}
        activeTab="preview"
        onActiveTabChange={vi.fn()}
        browserInput=""
        browserSrc=""
        onBrowserInputChange={vi.fn()}
        onBrowserSrcChange={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getAllByText("artifacts.loading").length).toBeGreaterThan(0)
    expect(screen.queryByText("artifacts.count")).not.toBeInTheDocument()
    expect(screen.getByRole("status", { name: "artifacts.loading" })).toBeInTheDocument()
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
    expect(input).toHaveAccessibleName("browser.urlPlaceholder")
    expect(screen.getByText("browser.empty")).toBeInTheDocument()
    expect(screen.queryByTitle("browser.title")).not.toBeInTheDocument()
  })
})

describe("resolveBrowserUrl", () => {
  it("allows external http and https URLs without falling back to the app route", () => {
    expect(
      resolveBrowserUrl(
        "https://bioinfoflow.example.evil.test/app",
        "https://bioinfoflow.example",
      ),
    ).toBe("https://bioinfoflow.example.evil.test/app")
    expect(resolveBrowserUrl("example.org/report", "https://bioinfoflow.example")).toBe(
      "https://example.org/report",
    )
  })

  it("normalizes absolute and relative URLs", () => {
    expect(
      resolveBrowserUrl(
        "https://bioinfoflow.example/agent?tab=browser#panel",
        "https://bioinfoflow.example",
      ),
    ).toBe("https://bioinfoflow.example/agent?tab=browser#panel")
    expect(resolveBrowserUrl("/runs", "https://bioinfoflow.example")).toBe(
      "https://bioinfoflow.example/runs",
    )
  })

  it("normalizes scheme-less local hosts as http URLs", () => {
    expect(resolveBrowserUrl("localhost:8000", "https://bioinfoflow.example")).toBe(
      "http://localhost:8000/",
    )
    expect(resolveBrowserUrl("127.0.0.1:8000/status", "https://bioinfoflow.example")).toBe(
      "http://127.0.0.1:8000/status",
    )
    expect(resolveBrowserUrl("[::1]:8000/report", "https://bioinfoflow.example")).toBe(
      "http://[::1]:8000/report",
    )
  })

  it("rejects empty and non-http URLs", () => {
    expect(resolveBrowserUrl("", "https://bioinfoflow.example")).toBe("")
    expect(resolveBrowserUrl("javascript:alert(1)", "https://bioinfoflow.example")).toBe("")
    expect(resolveBrowserUrl("ftp://example.org/file", "https://bioinfoflow.example")).toBe("")
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
