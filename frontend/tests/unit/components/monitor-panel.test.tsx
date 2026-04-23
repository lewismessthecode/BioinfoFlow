import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const useProjectContextMock = vi.fn()
const useEventsMock = vi.fn()
let latestEventOptions: Record<string, unknown> | null = null

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    const copy: Record<string, string> = {
      title: "Monitor",
      live: "Live",
      currentTask: "Current Task",
      taskStatus: "Task Status",
      "labels.status": "Status",
      "labels.tasksDone": "Tasks Done",
      "labels.remaining": "Remaining",
      "labels.run": "Run",
    }
    if (key === "progressSummary") {
      return `${values?.completed ?? 0}/${values?.total ?? 0} complete`
    }
    return copy[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/project-context", () => ({
  useProjectContext: (...args: unknown[]) => useProjectContextMock(...args),
}))

vi.mock("@/hooks/use-events", () => ({
  useEvents: (options: Record<string, unknown>) => {
    latestEventOptions = options
    return useEventsMock(options)
  },
}))

import { MonitorPanel } from "@/components/bioinfoflow/monitor-panel"

describe("MonitorPanel", () => {
  beforeEach(() => {
    latestEventOptions = null
    useProjectContextMock.mockReturnValue({ activeProjectId: "project-1" })
    useEventsMock.mockReturnValue({ connectionState: "connected" })
  })

  it("subscribes with the active project and shows the empty state by default", () => {
    const { container } = render(<MonitorPanel />)

    expect(useEventsMock).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: "project-1" }),
    )
    expect(screen.getByText("Current Task")).toBeInTheDocument()
    expect(screen.getAllByText("-").length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText("0/0 complete")).toBeInTheDocument()
    const indicator = container.querySelector('[data-slot="progress-indicator"]')
    expect(indicator).toHaveStyle({ transform: "translateX(-100%)" })
  })

  it("updates the run summary when a run.status event arrives", () => {
    const { container } = render(<MonitorPanel />)

    act(() => {
      const onRunStatus = latestEventOptions?.onRunStatus as
        | ((event: { data: { run_id: string; status: string; current_task: string; tasks_completed: number; tasks_total: number } }) => void)
        | undefined
      onRunStatus?.({
        data: {
          run_id: "run-42",
          status: "running",
          current_task: "ALIGN",
          tasks_completed: 3,
          tasks_total: 5,
        },
      })
    })

    expect(screen.getByText("ALIGN")).toBeInTheDocument()
    expect(screen.getByText("3/5 complete")).toBeInTheDocument()
    expect(screen.getByText("running")).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("run-42")).toBeInTheDocument()
    const indicator = container.querySelector('[data-slot="progress-indicator"]')
    expect(indicator).toHaveStyle({ transform: "translateX(-40%)" })
  })
})
