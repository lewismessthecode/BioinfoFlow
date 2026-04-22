import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import RunsPage from "@/app/(app)/runs/page"
import { ApiError, apiRequest } from "@/lib/api"
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
    ...props
  }: {
    href: string
    children: React.ReactNode
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
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

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    children,
  }: {
    open: boolean
    onOpenChange?: (open: boolean) => void
    children: React.ReactNode
  }) => (open ? <div data-testid="cancel-confirm-dialog">{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode; showCloseButton?: boolean }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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

describe("RunsPage - run actions", () => {
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

  it("shows detail loading failures and supports rerun plus cancel feedback", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [
            makeRun({ run_id: "run-1", status: "failed" }),
            makeRun({ run_id: "run-2", status: "running", id: "db-run-2" }),
          ],
          meta: { pagination: { total_count: 2, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        throw new ApiError("detail load failed", 404, "NOT_FOUND")
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/retry" && options?.method === "POST") {
        return { data: { run_id: "run-3", status: "queued" }, meta: undefined }
      }
      if (path === "/runs/run-2/cancel" && options?.method === "POST") {
        throw new ApiError("cancel failed", 409, "CONFLICT")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("detail load failed")
    })

    fireEvent.click(screen.getByText("detail-rerun"))

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("runs.toasts.resubmittedTitle:run-1", {
        description: "runs.toasts.checkRunsPage",
      })
    })

    fireEvent.click(await screen.findByRole("button", { name: "runs.cancelRun" }))
    expect(screen.getByTestId("cancel-confirm-dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common.confirm" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("cancel failed")
    })
  })

  it("supports resume success and refreshes the runs list", async () => {
    let runsFetchCount = 0

    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        runsFetchCount += 1
        return {
          data: [makeRun({ run_id: "run-1", status: runsFetchCount === 1 ? "failed" : "queued" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/resume" && options?.method === "POST") {
        return { data: { run_id: "run-1", status: "queued" }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-1")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "runs.resumeFromCheckpoint" }))

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("runs.toasts.resumedTitle:run-1", {
        description: "runs.toasts.executionQueued",
      })
      expect(runsFetchCount).toBe(2)
    })
  })

  it("shows an error toast when resume fails", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return { data: [], meta: undefined }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", status: "failed" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/resume" && options?.method === "POST") {
        throw new ApiError("resume failed", 409, "CONFLICT")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-1")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "runs.resumeFromCheckpoint" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("resume failed")
    })
  })

  it("shows an error toast when rerun fails from the detail view", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", status: "failed" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/retry" && options?.method === "POST") {
        throw new ApiError("retry failed", 409, "CONFLICT")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")
    fireEvent.click(screen.getByText("detail-rerun"))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("retry failed")
    })
  })

  it("keeps list state synchronized after cancel succeeds", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/runs/run-1/cancel" && options?.method === "POST") {
        return {
          data: makeRun({ run_id: "run-1", status: "cancelled" }),
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-status:running")
    fireEvent.click(screen.getByRole("button", { name: "runs.cancelRun" }))
    expect(screen.getByTestId("cancel-confirm-dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "common.confirm" }))

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("runs.toasts.cancelledTitle:run-1", {
        description: "runs.toasts.executionStopped",
      })
    })
  })

  it("shows a degraded detail state when outputs loading fails", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return { data: [], meta: undefined }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [{ message: "boot" }] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        throw new ApiError("outputs failed", 404, "FILE_NOT_FOUND")
      }
      if (path === "/runs/run-1/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("outputs failed")
    })
    expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-outputs:0")
  })

  it("shows a degraded detail state when dag loading fails", async () => {
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return { data: [], meta: undefined }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-1", status: "running" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-1/logs") {
        return { data: { logs: [{ message: "boot" }] }, meta: undefined }
      }
      if (path === "/runs/run-1/outputs") {
        return { data: { files: [{ path: "results/report.txt", name: "report.txt", type: "file" }] }, meta: undefined }
      }
      if (path === "/runs/run-1/dag") {
        throw new ApiError("dag failed", 404, "FILE_NOT_FOUND")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-1")
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("dag failed")
    })
    expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-dag:0")
  })

  it("opens logs from the list and deletes runs from the table actions", async () => {
    const deleteActions: Array<() => Promise<void>> = []

    searchParamsState.highlight = ""
    useEventsMock.mockReturnValue({ connectionState: "connected" })
    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        deleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [{ id: "wf-1", name: "viral-mini-nf", source: "nf-core", engine: "nextflow", version: "1.0.0" }],
          meta: undefined,
        }
      }
      if (path === "/runs") {
        return {
          data: [makeRun({ run_id: "run-delete", status: "failed" })],
          meta: { pagination: { total_count: 1, next_cursor: null } },
        }
      }
      if (path === "/runs/run-delete/logs") {
        return { data: { logs: [] }, meta: undefined }
      }
      if (path === "/runs/run-delete/outputs") {
        return { data: { files: [] }, meta: undefined }
      }
      if (path === "/runs/run-delete/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/runs/run-delete" && options?.method === "DELETE") {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<RunsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("run-delete")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "runs.viewLogs" }))

    await waitFor(() => {
      expect(toastInfoMock).toHaveBeenCalledWith("runs.toasts.openingLogsTitle:run-delete", {
        description: "runs.toasts.pipelineLabel:nf-core/viral-mini-nf",
      })
      expect(screen.getByTestId("run-inline-detail")).toHaveTextContent("detail-run:run-delete")
    })

    fireEvent.click(screen.getByRole("button", { name: "runs.deleteRun" }))
    expect(deleteActions).toHaveLength(1)
    await deleteActions[0]()

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("runs.toasts.deletedTitle:run-delete")
      expect(screen.getByText("runs.noRuns")).toBeInTheDocument()
    })
  })
})
