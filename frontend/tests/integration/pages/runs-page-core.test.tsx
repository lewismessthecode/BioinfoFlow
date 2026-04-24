import * as React from "react"
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import RunsPage from "@/app/(app)/runs/page"
import { apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const {
  toastErrorMock,
  toastInfoMock,
  toastSuccessMock,
  toastWarningMock,
} = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
  toastInfoMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastWarningMock: vi.fn(),
}))

const searchParamsState = {
  projectId: "project-url" as string | null,
  highlight: "run-1" as string | null,
  scope: null as "all" | "project" | null,
}

const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

const useEventsMock = vi.fn()
const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()

vi.mock("next/dynamic", () => ({
  default: (
    loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>,
    options?: { loading?: React.ComponentType<Record<string, unknown>> },
  ) => {
    return function DynamicMock(props: Record<string, unknown>) {
      const [Component, setComponent] = React.useState<React.ComponentType<Record<string, unknown>> | null>(null)

      React.useEffect(() => {
        let cancelled = false
        const timer = window.setTimeout(async () => {
          const loaded = await loader()
          if (!cancelled) {
            setComponent(() => loaded.default)
          }
        }, 0)

        return () => {
          cancelled = true
          window.clearTimeout(timer)
        }
      }, [])

      if (!Component) {
        const Loading = options?.loading
        return Loading ? <Loading /> : null
      }

      return <Component {...props} />
    }
  },
}))

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({
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
  }),
  useRouter: () => ({
    push: routerPushMock,
    replace: routerReplaceMock,
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/runs",
  useParams: () => ({}),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => {
    if (!translationMocks.has(namespace)) {
      translationMocks.set(
        namespace,
        (key: string, values?: Record<string, unknown>) => {
          const suffix = values
            ? Object.values(values)
                .filter((value) => value !== undefined && value !== null)
                .join(":")
            : ""
          return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
        }
      )
    }
    return translationMocks.get(namespace)!
  },
}))

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    onClick,
    ...props
  }: {
    href: string
    children: React.ReactNode
    onClick?: React.MouseEventHandler<HTMLAnchorElement>
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a
      href={href}
      {...props}
      onClick={(event) => {
        event.preventDefault()
        onClick?.(event)
      }}
    >
      {children}
    </a>
  ),
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

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

vi.mock("@/app/(app)/runs/components/runs-table-skeleton", () => ({
  RunsTableSkeleton: () => <div data-testid="runs-skeleton" />,
}))

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuCheckboxItem: ({
    checked,
    onCheckedChange,
    children,
  }: {
    checked?: boolean
    onCheckedChange?: (checked: boolean) => void
    children: React.ReactNode
  }) => (
    <button role="checkbox" aria-checked={checked} onClick={() => onCheckedChange?.(!checked)}>
      {children}
    </button>
  ),
}))

vi.mock("@/components/ui/tabs", () => {
  const TabsContext = React.createContext<{
    value: string
    onValueChange: (value: string) => void
  } | null>(null)

  return {
    Tabs: ({
      value,
      onValueChange,
      children,
    }: {
      value: string
      onValueChange: (value: string) => void
      children: React.ReactNode
    }) => (
      <TabsContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    TabsTrigger: ({
      value,
      disabled,
      children,
    }: {
      value: string
      disabled?: boolean
      children: React.ReactNode
    }) => {
      const context = React.useContext(TabsContext)
      return (
        <button
          role="tab"
          aria-selected={context?.value === value}
          disabled={disabled}
          onClick={() => context?.onValueChange(value)}
        >
          {children}
        </button>
      )
    },
  }
})

vi.mock("@/components/ui/status-badge", () => ({
  StatusBadge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock("@/components/ui/empty-state", () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}))

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  },
}))

vi.mock("@/app/(app)/runs/components/run-inline-detail", () => ({
  RunInlineDetail: ({
    run,
    logs,
    outputs,
    dag,
    workflowName,
    colSpan,
    onRerun,
  }: {
    run: { run_id: string; status: string }
    logs: { logs: unknown[] } | null
    outputs: { files: unknown[] } | null
    dag: { nodes?: unknown[] } | null
    workflowName: string
    colSpan: number
    onRerun: (run: { run_id: string; status: string }) => void
  }) => (
    <tr data-testid="run-inline-detail">
      <td colSpan={colSpan}>
        <div>detail-run:{run.run_id}</div>
        <div>detail-status:{run.status}</div>
        <div>detail-logs:{logs?.logs.length ?? 0}</div>
        <div>detail-outputs:{outputs?.files.length ?? 0}</div>
        <div>detail-dag:{dag?.nodes?.length ?? 0}</div>
        <div>detail-workflow:{workflowName}</div>
        <button onClick={() => onRerun(run)}>detail-rerun</button>
      </td>
    </tr>
  ),
}))

describe("RunsPage - core features", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  const makeRun = (overrides: Record<string, unknown> = {}) => ({
    id: String(overrides.id ?? "db-run-1"),
    run_id: String(overrides.run_id ?? "run-1"),
    project_id: String(overrides.project_id ?? "project-url"),
    workflow_id: String(overrides.workflow_id ?? "wf-1"),
    status: String(overrides.status ?? "failed"),
    workspace: ".",
    config: {},
    samples_count: 2,
    tasks_total: 4,
    tasks_completed: 1,
    current_task: null,
    duration_seconds: 12,
    started_at: "2026-03-16T00:00:00Z",
    completed_at: null,
  })

  beforeEach(() => {
    apiRequestMock.mockReset()
    useEventsMock.mockReset()
    toastErrorMock.mockReset()
    toastInfoMock.mockReset()
    toastSuccessMock.mockReset()
    toastWarningMock.mockReset()
    routerPushMock.mockReset()
    routerReplaceMock.mockReset()
    searchParamsState.projectId = "project-url"
    searchParamsState.highlight = "run-1"
    searchParamsState.scope = null
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("initializes from URL params and keeps list/detail in sync with SSE updates", async () => {
    let outputsFetches = 0
    let eventHandlers:
      | {
          onRunStatus?: (event: { data: { run_id: string; status: string; current_task?: string; tasks_completed?: number; tasks_total?: number } }) => void
          onRunLog?: (event: { data: { run_id: string; message: string; level?: string; task?: string; timestamp?: string } }) => void
          onRunDag?: (event: { data: { run_id: string; dag: { nodes: unknown[] } } }) => void
        }
      | undefined

    useEventsMock.mockImplementation((options) => {
      eventHandlers = options
      return { connectionState: "connected" }
    })

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        expect(options?.params?.project_id).toBe("project-url")
        return {
          data: [makeRun({ status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [{ message: "boot" }] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
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
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [{ id: "task-1" }], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-context" },
    })

    expect(await screen.findByText("run-1")).toBeInTheDocument()
    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")
    await waitFor(() => {
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-status:running")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-logs:1")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-outputs:0")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-dag:1")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-workflow:nf-core/viral-mini-nf")
    })

    await act(async () => {
      eventHandlers?.onRunStatus?.({
        data: {
          run_id: "run-1",
          status: "completed",
          current_task: "done",
          tasks_completed: 4,
          tasks_total: 4,
        },
      })
      eventHandlers?.onRunLog?.({
        data: {
          run_id: "run-1",
          message: "finished",
          level: "info",
          task: "align",
          timestamp: "2026-03-16T00:01:00Z",
        },
      })
      eventHandlers?.onRunDag?.({
        data: {
          run_id: "run-1",
          dag: { nodes: [{ id: "task-1" }, { id: "task-2" }] },
        },
      })
    })

    await waitFor(() => {
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-status:completed")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-logs:2")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-outputs:1")
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-dag:2")
    })
  })

  it("loads all runs for global scope and switches back to project scope on demand", async () => {
    const runsCalls: Array<Record<string, unknown>> = []

    useEventsMock.mockReturnValue({ connectionState: "connected" })
    searchParamsState.projectId = null
    searchParamsState.highlight = null
    searchParamsState.scope = "all"

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [
            { id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" },
          ],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        runsCalls.push({ ...(options?.params ?? {}) })
        const isProjectScope = options?.params?.project_id === "project-context"
        return {
          data: [
            makeRun({
              run_id: isProjectScope ? "run-project" : "run-global",
              project_id: isProjectScope ? "project-context" : "project-other",
              status: "running",
            }),
          ],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (String(path).startsWith("/runs/run-")) {
        if (String(path).endsWith("/logs")) return { data: { logs: [] }, meta: undefined }
        if (String(path).endsWith("/outputs")) return { data: { files: [] }, meta: undefined }
        if (String(path).endsWith("/dag")) return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-context" },
    })

    expect(await screen.findByText("run-global")).toBeInTheDocument()
    expect(runsCalls[0]).toMatchObject({
      project_id: undefined,
    })
    expect(useEventsMock).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: undefined })
    )

    fireEvent.click(screen.getByRole("tab", { name: "runs.scopes.project" }))

    expect(await screen.findByText("run-project")).toBeInTheDocument()
    expect(runsCalls.at(-1)).toMatchObject({
      project_id: "project-context",
    })
    expect(routerReplaceMock).toHaveBeenCalledWith("/runs?scope=project")
  })

  it("resets the cursor when the status filter changes", async () => {
    const runsCalls: Array<Record<string, unknown>> = []

    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return { data: [], meta: undefined }
      }
      if (path === "/runs") {
        runsCalls.push({ ...(options?.params ?? {}) })
        return {
          data: [makeRun({ run_id: `run-${runsCalls.length}`, status: "running" })],
          meta: {
            pagination: {
              total_count: 2,
              next_cursor: runsCalls.length === 1 ? "cursor-1" : null,
            },
          },
        }
      }
      if (String(path).startsWith("/runs/run-")) {
        if (String(path).endsWith("/logs")) return { data: { logs: [] }, meta: undefined }
        if (String(path).endsWith("/outputs")) return { data: { files: [] }, meta: undefined }
        if (String(path).endsWith("/dag")) return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-1")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("checkbox", { name: "status.running" }))

    await waitFor(() => {
      expect(runsCalls.at(-1)).toMatchObject({
        project_id: "project-url",
        status: "running",
        cursor: undefined,
      })
    })
  })

  it("tracks cursor history across next and previous pagination", async () => {
    const requestedCursors: Array<string | undefined> = []

    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return { data: [], meta: undefined }
      }
      if (path === "/runs") {
        requestedCursors.push(options?.params?.cursor as string | undefined)
        const currentCursor = options?.params?.cursor as string | undefined
        return {
          data: [
            makeRun({
              run_id: currentCursor === "cursor-1" ? "run-2" : "run-1",
              status: "running",
            }),
          ],
          meta: {
            pagination: {
              total_count: 2,
              next_cursor: currentCursor ? null : "cursor-1",
            },
          },
        }
      }
      if (String(path).startsWith("/runs/run-")) {
        if (String(path).endsWith("/logs")) return { data: { logs: [] }, meta: undefined }
        if (String(path).endsWith("/outputs")) return { data: { files: [] }, meta: undefined }
        if (String(path).endsWith("/dag")) return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-1")).toBeInTheDocument()

    const paginationControls = screen.getByText("runs.pagination.page:1").parentElement
    const [prevButton, nextButton] = within(paginationControls as HTMLElement).getAllByRole("button")

    fireEvent.click(nextButton)
    expect(await screen.findByText("run-2")).toBeInTheDocument()
    expect(screen.getByText("runs.pagination.page:2")).toBeInTheDocument()

    fireEvent.click(prevButton)
    expect(await screen.findByText("run-1")).toBeInTheDocument()
    expect(screen.getByText("runs.pagination.page:1")).toBeInTheDocument()
    expect(requestedCursors).toEqual([undefined, "cursor-1", undefined])
  })

  it("filters runs by search text across run id and workflow name", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [
            makeRun({ run_id: "run-alpha", workflow_id: "wf-1", status: "running" }),
            makeRun({ run_id: "run-beta", workflow_id: "wf-2", status: "failed", id: "db-run-2" }),
          ],
          meta: { pagination: { total_count: 2, next_cursor: null } },
        }
      }
      if (String(path).startsWith("/runs/run-")) {
        if (String(path).endsWith("/logs")) return { data: { logs: [] }, meta: undefined }
        if (String(path).endsWith("/outputs")) return { data: { files: [] }, meta: undefined }
        if (String(path).endsWith("/dag")) return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-alpha")).toBeInTheDocument()
    expect(screen.getByText("run-beta")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("common.search runs.title"), {
      target: { value: "viral-mini" },
    })
    expect(await screen.findByText("run-alpha")).toBeInTheDocument()
    expect(screen.queryByText("run-beta")).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("common.search runs.title"), {
      target: { value: "run-beta" },
    })
    expect(await screen.findByText("run-beta")).toBeInTheDocument()
    expect(screen.queryByText("run-alpha")).not.toBeInTheDocument()
  })

  it("does not reopen a highlighted run after the user closes it", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        expect(options?.params?.project_id).toBe("project-url")
        return {
          data: [makeRun({ run_id: "run-1", workflow_id: "wf-1", status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") return { data: { logs: [] }, meta: undefined }
      if (path === "/runs/run-1/outputs") return { data: { files: [] }, meta: undefined }
      if (path === "/runs/run-1/dag") return { data: { nodes: [], edges: [] }, meta: undefined }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")

    fireEvent.click(screen.getByRole("button", { name: "runs.viewDetails" }))

    await waitFor(() => {
      expect(screen.queryByTestId("run-inline-detail")).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole("checkbox", { name: "status.running" }))

    await waitFor(() => {
      expect(screen.queryByTestId("run-inline-detail")).not.toBeInTheDocument()
    })
  })

  it("shows an inline loading placeholder before the heavy detail chunk resolves", async () => {
    searchParamsState.highlight = null
    useEventsMock.mockReturnValue({ connectionState: "connected" })

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", workflow_id: "wf-1", status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") return { data: { logs: [] }, meta: undefined }
      if (path === "/runs/run-1/outputs") return { data: { files: [] }, meta: undefined }
      if (path === "/runs/run-1/dag") return { data: { nodes: [], edges: [] }, meta: undefined }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-1")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "runs.viewDetails" }))

    expect(screen.getByTestId("run-inline-detail-loading")).toBeInTheDocument()
    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")
  })

  it("renders workflow names as links without expanding the row", async () => {
    searchParamsState.highlight = null
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", workflow_id: "wf-1", status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    const workflowLink = await screen.findByRole("link", { name: "nf-core/viral-mini-nf" })
    expect(workflowLink).toHaveAttribute("href", "/workflows/wf-1")

    fireEvent.click(workflowLink)

    expect(screen.queryByTestId("run-inline-detail")).not.toBeInTheDocument()
  })
})
