import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useRunsPage } from "@/app/(app)/runs/use-runs-page"
import { apiRequest, buildApiUrl } from "@/lib/api"
import { createAppWrapper } from "@/tests/app-test-utils"

const {
  routerPushMock,
  routerReplaceMock,
  routerBackMock,
  routerForwardMock,
  routerRefreshMock,
  routerPrefetchMock,
  toastErrorMock,
  toastInfoMock,
  toastSuccessMock,
  toastWarningMock,
  openInNewTabMock,
  celebrateMilestoneMock,
} = vi.hoisted(() => ({
  routerPushMock: vi.fn(),
  routerReplaceMock: vi.fn(),
  routerBackMock: vi.fn(),
  routerForwardMock: vi.fn(),
  routerRefreshMock: vi.fn(),
  routerPrefetchMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastInfoMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastWarningMock: vi.fn(),
  openInNewTabMock: vi.fn(),
  celebrateMilestoneMock: vi.fn(),
}))

const searchParamsState = {
  projectId: "project-url" as string | null,
  highlight: "run-1" as string | null,
  scope: null as "all" | "project" | null,
}

const stableSearchParams = {
  get: (key: string) => {
    if (key === "project_id") return searchParamsState.projectId
    if (key === "highlight") return searchParamsState.highlight
    if (key === "scope") return searchParamsState.scope
    return null
  },
  toString: () => {
    const params = new URLSearchParams()
    if (searchParamsState.projectId) params.set("project_id", searchParamsState.projectId)
    if (searchParamsState.highlight) params.set("highlight", searchParamsState.highlight)
    if (searchParamsState.scope) params.set("scope", searchParamsState.scope)
    return params.toString()
  },
}

const stableRouter = {
  push: routerPushMock,
  replace: routerReplaceMock,
  back: routerBackMock,
  forward: routerForwardMock,
  refresh: routerRefreshMock,
  prefetch: routerPrefetchMock,
}

const translationMap = new Map<string, (key: string, values?: Record<string, unknown>) => string>()

function getTranslation(namespace: string) {
  if (!translationMap.has(namespace)) {
    translationMap.set(namespace, (key: string, values?: Record<string, unknown>) => {
      const suffix = values
        ? Object.values(values)
            .filter((value) => value !== undefined && value !== null)
            .join(":")
        : ""
      return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
    })
  }
  return translationMap.get(namespace)!
}

const useEventsMock = vi.fn()

vi.mock("next/navigation", () => ({
  useSearchParams: () => stableSearchParams,
  useRouter: () => stableRouter,
  usePathname: () => "/runs",
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => getTranslation(namespace),
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    info: toastInfoMock,
    success: toastSuccessMock,
    warning: toastWarningMock,
  },
}))

vi.mock("@/hooks/use-events", () => ({
  useEvents: (...args: unknown[]) => useEventsMock(...args),
}))

vi.mock("@/lib/window-utils", () => ({
  openInNewTab: (...args: unknown[]) => openInNewTabMock(...args),
}))

vi.mock("@/lib/celebrations", () => ({
  celebrateMilestone: (...args: unknown[]) => celebrateMilestoneMock(...args),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
    buildApiUrl: vi.fn(() => "/download"),
  }
})

describe("useRunsPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const buildApiUrlMock = vi.mocked(buildApiUrl)

  const makeWorkflow = (overrides: Record<string, unknown> = {}) => ({
    id: String(overrides.id ?? "wf-1"),
    name: String(overrides.name ?? "rna-qc"),
    source: String(overrides.source ?? "local"),
    version: String(overrides.version ?? "1.0.0"),
    engine: String(overrides.engine ?? "nextflow"),
    description: String(overrides.description ?? "workflow"),
    updated_at: String(overrides.updated_at ?? "2026-04-23T00:00:00.000Z"),
  })

  const makeRun = (overrides: Record<string, unknown> = {}) => ({
    id: String(overrides.id ?? "db-run-1"),
    run_id: String(overrides.run_id ?? "run-1"),
    project_id: String(overrides.project_id ?? "project-url"),
    workflow_id: String(overrides.workflow_id ?? "wf-1"),
    status: String(overrides.status ?? "running"),
    workspace: ".",
    config: {},
    samples_count: 1,
    tasks_total: 2,
    tasks_completed: 1,
    current_task: null,
    duration_seconds: 4,
    started_at: "2026-04-23T00:00:00.000Z",
    completed_at: null,
  })

  beforeEach(() => {
    searchParamsState.projectId = "project-url"
    searchParamsState.highlight = null
    searchParamsState.scope = null
    apiRequestMock.mockReset()
    buildApiUrlMock.mockClear()
    routerPushMock.mockReset()
    routerReplaceMock.mockReset()
    routerBackMock.mockReset()
    routerForwardMock.mockReset()
    routerRefreshMock.mockReset()
    routerPrefetchMock.mockReset()
    toastErrorMock.mockReset()
    toastInfoMock.mockReset()
    toastSuccessMock.mockReset()
    toastWarningMock.mockReset()
    openInNewTabMock.mockReset()
    celebrateMilestoneMock.mockReset()
    useEventsMock.mockReset()
    useEventsMock.mockReturnValue({ connectionState: "connected" })
  })

  it("syncs the URL project into context and auto-expands a highlighted run", async () => {
    searchParamsState.highlight = "run-1"

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return { data: [makeWorkflow()], meta: undefined }
      }
      if (path === "/runs") {
        return {
          data: [makeRun()],
          meta: { pagination: { next_cursor: null, prev_cursor: null, has_more: false } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [{ message: "started", level: "info", task: null, timestamp: null }] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [{ id: "node-1" }], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ hook: useRunsPage(), project: useProjectContext() }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.project.activeProjectId).toBe("project-url"))
    await waitFor(() => expect(result.current.hook.filteredRuns).toHaveLength(1))
    await waitFor(() => expect(result.current.hook.expandedRunId).toBe("run-1"))
    await waitFor(() => expect(result.current.hook.logs?.logs).toHaveLength(1))
    expect(result.current.hook.dag?.nodes).toHaveLength(1)
    expect(routerReplaceMock).toHaveBeenCalledWith("/runs?project_id=project-url")
  })

  it("appends live logs and refreshes outputs when an expanded run reaches a terminal status", async () => {
    searchParamsState.highlight = null

    let eventHandlers:
      | {
          onRunStatus?: (event: {
            data: {
              run_id: string
              status: "running" | "completed" | "failed" | "cancelled"
              current_task?: string | null
              tasks_completed?: number
              tasks_total?: number
            }
          }) => void
          onRunLog?: (event: {
            data: {
              run_id: string
              message: string
              level?: string | null
              task?: string | null
              timestamp?: string | null
            }
          }) => void
        }
      | undefined
    let outputsFetches = 0

    useEventsMock.mockImplementation((options) => {
      eventHandlers = options
      return { connectionState: "connected" }
    })

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return { data: [makeWorkflow()], meta: undefined }
      }
      if (path === "/runs") {
        return {
          data: [makeRun()],
          meta: { pagination: { next_cursor: null, prev_cursor: null, has_more: false } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        outputsFetches += 1
        return {
          data: {
            files: outputsFetches > 1 ? [{ path: "results/hello.txt", name: "hello.txt", type: "file" }] : [],
          },
          meta: undefined,
        }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-url",
    })
    const { result } = renderHook(() => useRunsPage(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.filteredRuns).toHaveLength(1))

    await act(async () => {
      result.current.toggleExpand(result.current.filteredRuns[0]!)
    })

    await waitFor(() => expect(result.current.expandedRunId).toBe("run-1"))
    await waitFor(() => expect(outputsFetches).toBe(1))

    act(() => {
      eventHandlers?.onRunLog?.({
        data: {
          run_id: "run-1",
          message: "stream update",
          level: "info",
          task: "WRITE_HELLO",
          timestamp: "2026-04-23T00:10:00.000Z",
        },
      })
    })

    await waitFor(() =>
      expect(result.current.logs?.logs.at(-1)).toMatchObject({
        message: "stream update",
        task: "WRITE_HELLO",
      }),
    )

    act(() => {
      eventHandlers?.onRunStatus?.({
        data: {
          run_id: "run-1",
          status: "completed",
          tasks_completed: 2,
          tasks_total: 2,
        },
      })
    })

    await waitFor(() => expect(result.current.outputs?.files).toHaveLength(1))
    expect(result.current.filteredRuns[0]?.status).toBe("completed")
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-run-success")
  })

  it("surfaces container image preparation logs as a toast", async () => {
    let eventHandlers:
      | {
          onRunLog?: (event: {
            data: {
              run_id: string
              message: string
              level?: string | null
              task?: string | null
              timestamp?: string | null
            }
          }) => void
        }
      | undefined

    useEventsMock.mockImplementation((options) => {
      eventHandlers = options
      return { connectionState: "connected" }
    })

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return { data: [makeWorkflow()], meta: undefined }
      }
      if (path === "/runs") {
        return {
          data: [makeRun()],
          meta: { pagination: { next_cursor: null, prev_cursor: null, has_more: false } },
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-url",
    })
    renderHook(() => useRunsPage(), { wrapper: Wrapper })

    await waitFor(() => expect(eventHandlers?.onRunLog).toBeDefined())

    act(() => {
      eventHandlers?.onRunLog?.({
        data: {
          run_id: "run-1",
          message: "Preparing required container images: nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
          level: "info",
          task: null,
          timestamp: "2026-04-29T01:15:14.000Z",
        },
      })
    })

    expect(toastInfoMock).toHaveBeenCalledWith(
      "runs.toasts.preparingImagesTitle",
      {
        description: "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
      },
    )
  })

  it("updates the URL and refetches runs around a newly submitted run", async () => {
    let runsFetches = 0
    const runRequestParams: Array<Record<string, unknown> | undefined> = []

    searchParamsState.highlight = null

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return { data: [makeWorkflow()], meta: undefined }
      }
      if (path === "/runs") {
        runsFetches += 1
        runRequestParams.push(options?.params)
        return {
          data: runsFetches > 1 ? [makeRun({ run_id: "run-99" })] : [makeRun()],
          meta: { pagination: { next_cursor: null, prev_cursor: null, has_more: false } },
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-url",
    })
    const { result } = renderHook(() => useRunsPage(), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.filteredRuns).toHaveLength(1))

    await act(async () => {
      await result.current.handleSubmittedRun("run-99")
    })

    const latestUrl = routerReplaceMock.mock.calls.at(-1)?.[0]
    expect(latestUrl).toBeDefined()
    const [, query = ""] = String(latestUrl).split("?")
    const params = new URLSearchParams(query)
    expect(String(latestUrl).startsWith("/runs?")).toBe(true)
    expect(params.get("project_id")).toBe("project-url")
    expect(params.get("highlight")).toBe("run-99")
    expect(params.get("scope")).toBe("project")
    await waitFor(() => expect(result.current.filteredRuns[0]?.run_id).toBe("run-99"))
    expect(result.current.expandedRunId).toBe("run-99")
    expect(runRequestParams).toEqual([
      expect.objectContaining({
        cursor: undefined,
        limit: 20,
        project_id: "project-url",
        status: undefined,
      }),
      expect.objectContaining({
        cursor: undefined,
        limit: 20,
        project_id: "project-url",
        status: undefined,
      }),
    ])
  })
})
