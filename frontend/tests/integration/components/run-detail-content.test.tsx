import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RunDetailContent } from "@/app/(app)/runs/components/run-detail-content"
import type { DagData, Run } from "@/lib/types"
import { renderAppPage } from "@/tests/app-test-utils"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))

vi.mock("@/components/bioinfoflow/dag", () => ({
  DagPanel: ({
    runId,
    workflowName,
  }: {
    runId?: string | null
    workflowName?: string
  }) => <div data-testid="dag-panel">{`${runId ?? "no-run"}:${workflowName ?? "no-workflow"}`}</div>,
}))

const openTerminalMock = vi.fn()
const chdirMock = vi.fn()
let terminalIsOpen = false

vi.mock("@/components/bioinfoflow/terminal/terminal-dock-context", () => ({
  useTerminalDock: () => ({
    isOpen: terminalIsOpen,
    openTerminal: openTerminalMock,
    chdir: chdirMock,
  }),
}))

const run: Run = {
  id: "db-run-1",
  run_id: "run-1",
  project_id: "project-1",
  workflow_id: "wf-1",
  status: "completed",
  workspace: ".",
  config: {},
  samples_count: 1,
  tasks_total: 3,
  tasks_completed: 3,
  current_task: null,
  duration_seconds: 4,
  started_at: "2026-03-16T11:35:52Z",
  completed_at: "2026-03-16T11:35:56Z",
}

const dag: DagData = {
  nodes: [
    {
      id: "task-1",
      type: "pipeline",
      position: { x: 20, y: 40 },
      data: {
        label: "TASK_1",
        status: "success",
      },
    },
  ],
  edges: [],
}

describe("RunDetailContent", () => {
  beforeEach(() => {
    terminalIsOpen = false
    openTerminalMock.mockClear()
    chdirMock.mockClear()
  })

  it("keeps the active DAG tab in normal layout flow for the full-page variant", () => {
    renderAppPage(
      <div className="h-[640px]">
        <RunDetailContent
          run={run}
          logs={{ logs: [] }}
          outputs={{ files: [] }}
          dag={dag}
          workflowName="viral-mini-nf"
          projectId="project-1"
          variant="fullpage"
          onDownloadResults={vi.fn()}
          onRerun={vi.fn()}
          onDelete={vi.fn()}
          onDownloadFile={vi.fn()}
          onOpenDagFullscreen={vi.fn()}
        />
      </div>
    )

    const dagTabPanel = screen.getByRole("tabpanel", { name: "runs.detail.tabs.dag" })

    expect(dagTabPanel).toBeInTheDocument()
    expect(dagTabPanel).not.toHaveClass("absolute")
    expect(dagTabPanel).toHaveClass("flex-1", "min-h-0")
    expect(dagTabPanel.closest('[data-slot="tabs"]')).toHaveClass("h-full")
    expect(screen.getByTestId("dag-panel")).toHaveTextContent("run-1:viral-mini-nf")
  })

  it("constrains the inline DAG viewport with a fixed max height", () => {
    renderAppPage(
      <RunDetailContent
        run={run}
        logs={{ logs: [] }}
        outputs={{ files: [] }}
        dag={dag}
        workflowName="viral-mini-nf"
        projectId="project-1"
        variant="inline"
        onDownloadResults={vi.fn()}
        onRerun={vi.fn()}
        onDelete={vi.fn()}
        onDownloadFile={vi.fn()}
        onOpenDagFullscreen={vi.fn()}
      />
    )

    const dagFrame = screen.getByTestId("dag-panel").parentElement
    expect(dagFrame).toHaveClass("h-[420px]")
    expect(screen.getByTestId("dag-panel")).toHaveTextContent("run-1:viral-mini-nf")
  })

  it("keeps terminal directory actions hidden until the dock is open", async () => {
    const user = userEvent.setup()
    renderAppPage(
      <RunDetailContent
        run={{ ...run, workspace: "runs/run-1" }}
        logs={{ logs: [] }}
        outputs={{ files: [] }}
        dag={dag}
        workflowName="viral-mini-nf"
        projectId="project-1"
        variant="fullpage"
        onDownloadResults={vi.fn()}
        onRerun={vi.fn()}
        onDelete={vi.fn()}
        onDownloadFile={vi.fn()}
      />
    )

    // Primary actions are directly visible buttons
    expect(screen.getByRole("button", { name: "runs.rerunPipeline" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "runs.downloadResults" })).toBeInTheDocument()

    // Terminal actions must not open or queue commands while the dock is closed.
    const overflowTrigger = screen.getByRole("button", { name: "" })
    expect(overflowTrigger).toHaveAttribute("aria-haspopup", "menu")
    await user.click(overflowTrigger)
    expect(screen.queryByText("runs.goToRunDir")).not.toBeInTheDocument()
    expect(openTerminalMock).not.toHaveBeenCalled()
    expect(chdirMock).not.toHaveBeenCalled()
  })

  it("changes to the run directory from the menu when the terminal is already open", async () => {
    terminalIsOpen = true
    const user = userEvent.setup()
    renderAppPage(
      <RunDetailContent
        run={{ ...run, workspace: "runs/run-1" }}
        logs={{ logs: [] }}
        outputs={{ files: [] }}
        dag={dag}
        workflowName="viral-mini-nf"
        projectId="project-1"
        variant="fullpage"
        onDownloadResults={vi.fn()}
        onRerun={vi.fn()}
        onDelete={vi.fn()}
        onDownloadFile={vi.fn()}
      />
    )

    await user.click(screen.getByRole("button", { name: "" }))
    await user.click(screen.getByText("runs.goToRunDir"))

    expect(chdirMock).toHaveBeenCalledWith("runs/run-1")
    expect(openTerminalMock).not.toHaveBeenCalled()
  })
})
