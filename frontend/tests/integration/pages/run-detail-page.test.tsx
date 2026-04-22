import { screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import RunDetailPage from "@/app/(app)/runs/[runId]/page"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const { toastErrorMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
}))
const { translateMock } = vi.hoisted(() => ({
  translateMock: vi.fn((key: string) => key),
}))
const { useEventsMock } = vi.hoisted(() => ({
  useEventsMock: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useParams: () => ({ runId: "run-123" }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => translateMock,
}))

vi.mock("next/dynamic", () => ({
  default: () => () => null,
}))

vi.mock("@/hooks/use-events", () => ({
  useEvents: (...args: unknown[]) => useEventsMock(...args),
}))

vi.mock("@/app/(app)/runs/components/run-detail-content", () => ({
  RunDetailContent: ({
    run,
    outputs,
  }: {
    run: { run_id: string }
    outputs: { files?: unknown[] } | null
  }) => (
    <div data-testid="run-detail-content">
      {run.run_id}:outputs:{outputs?.files?.length ?? 0}
    </div>
  ),
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
    getApiErrorMessage: vi.fn((_error: unknown, fallback: string) => fallback),
    buildApiUrl: vi.fn(() => "/download"),
  }
})

function ProjectContextProbe() {
  const { activeProjectId } = useProjectContext()
  return <div data-testid="active-project-id">{activeProjectId || "none"}</div>
}

describe("RunDetailPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
    toastErrorMock.mockReset()
    useEventsMock.mockReset()
    useEventsMock.mockReturnValue({ connectionState: "connected" })

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/runs/run-123") {
        return {
          data: {
            id: "run-model-id",
            run_id: "run-123",
            project_id: "project-from-run",
            workflow_id: "workflow-1",
            status: "running",
            workspace: ".",
            config: {},
            samples_count: 1,
            tasks_total: 4,
            tasks_completed: 1,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-1") {
        return {
          data: {
            id: "workflow-1",
            name: "RNA QC",
            source: "github",
            engine: "nextflow",
            version: "1.0.0",
          },
          meta: undefined,
        }
      }
      if (path === "/runs/run-123/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-123/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-123/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("syncs the active project from the fetched run when opened directly", async () => {
    renderAppPage(
      <>
        <ProjectContextProbe />
        <RunDetailPage />
      </>
    )

    expect(screen.getByTestId("active-project-id")).toHaveTextContent("none")
    expect(await screen.findByTestId("run-detail-content")).toHaveTextContent("run-123")

    await waitFor(() => {
      expect(screen.getByTestId("active-project-id")).toHaveTextContent(
        "project-from-run"
      )
    })
  })

  it("refreshes outputs after the run reaches a terminal state", async () => {
    let outputsFetches = 0
    let eventHandlers:
      | {
          onRunStatus?: (event: {
            data: {
              run_id: string
              status: string
              current_task?: string
              tasks_completed?: number
              tasks_total?: number
            }
          }) => void
        }
      | undefined

    useEventsMock.mockImplementation((options) => {
      eventHandlers = options
      return { connectionState: "connected" }
    })

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/runs/run-123") {
        return {
          data: {
            id: "run-model-id",
            run_id: "run-123",
            project_id: "project-from-run",
            workflow_id: "workflow-1",
            status: "running",
            workspace: ".",
            config: {},
            samples_count: 1,
            tasks_total: 4,
            tasks_completed: 1,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-1") {
        return {
          data: {
            id: "workflow-1",
            name: "RNA QC",
            source: "github",
            engine: "nextflow",
            version: "1.0.0",
          },
          meta: undefined,
        }
      }
      if (path === "/runs/run-123/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-123/outputs") {
        outputsFetches += 1
        return {
          data: {
            files:
              outputsFetches > 1
                ? [{ path: "results/report.txt", name: "report.txt", type: "file" }]
                : [],
          },
          meta: undefined,
        }
      }
      if (path === "/runs/run-123/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunDetailPage />)

    expect(await screen.findByTestId("run-detail-content")).toHaveTextContent(
      "run-123:outputs:0"
    )

    eventHandlers?.onRunStatus?.({
      data: {
        run_id: "run-123",
        status: "completed",
        tasks_completed: 4,
        tasks_total: 4,
      },
    })

    await waitFor(() => {
      expect(screen.getByTestId("run-detail-content")).toHaveTextContent(
        "run-123:outputs:1"
      )
    })
  })
})
