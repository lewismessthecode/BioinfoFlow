import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import WorkflowDetailPage from "@/app/(app)/workflows/[id]/page"
import { ApiError, apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const {
  pushMock,
  toastErrorMock,
  toastSuccessMock,
  clipboardWriteTextMock,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  clipboardWriteTextMock: vi.fn(),
}))

const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "workflow-123" }),
  useRouter: () => ({ push: pushMock }),
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

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

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
      children,
    }: {
      value: string
      children: React.ReactNode
    }) => {
      const context = React.useContext(TabsContext)
      return (
        <button
          role="tab"
          aria-selected={context?.value === value}
          onClick={() => context?.onValueChange(value)}
        >
          {children}
        </button>
      )
    },
    TabsContent: ({
      value,
      children,
    }: {
      value: string
      children: React.ReactNode
    }) => {
      const context = React.useContext(TabsContext)
      return context?.value === value ? <div>{children}</div> : null
    },
  }
})

vi.mock("@/app/(app)/workflows/[id]/components/workflow-overview-tab", () => ({
  WorkflowOverviewTab: ({
    workflow,
  }: {
    workflow: { name: string }
  }) => <div data-testid="overview-tab">{workflow.name}</div>,
}))

vi.mock("@/app/(app)/workflows/[id]/components/workflow-parameters-tab", () => ({
  WorkflowParametersTab: () => <div data-testid="parameters-tab">parameters-tab</div>,
}))

vi.mock("@/app/(app)/workflows/[id]/components/workflow-tasks-tab", () => ({
  WorkflowTasksTab: () => <div data-testid="tasks-tab">tasks-tab</div>,
}))

vi.mock("@/app/(app)/workflows/[id]/components/workflow-source-tab", () => ({
  WorkflowSourceTab: ({
    source,
    workflowSource,
    compareCandidates,
    selectedCompareWorkflowId,
    compareSource,
    onCompareWorkflowChange,
  }: {
    source: string | null
    workflowSource: string
    compareCandidates?: Array<{ id: string; version: string }>
    selectedCompareWorkflowId?: string | null
    compareSource?: string | null
    onCompareWorkflowChange?: (value: string) => void
  }) => (
    <div data-testid="source-tab">
      <div>{workflowSource}:{source ?? "empty"}</div>
      <div>compare-count:{compareCandidates?.length ?? 0}</div>
      <div>compare-selected:{selectedCompareWorkflowId ?? "empty"}</div>
      <div>compare-source:{compareSource ?? "empty"}</div>
      {compareCandidates?.[0] && onCompareWorkflowChange ? (
        <button
          type="button"
          onClick={() => onCompareWorkflowChange(compareCandidates[0].id)}
        >
          mock-compare-select
        </button>
      ) : null}
    </div>
  ),
}))

vi.mock("@/components/bioinfoflow/dag", () => ({
  DagPanel: ({
    dag,
    workflowId,
  }: {
    dag: { nodes?: unknown[] } | null
    workflowId: string
  }) => (
    <div data-testid="dag-panel">
      {workflowId}:{dag?.nodes?.length ?? 0}
    </div>
  ),
}))

describe("WorkflowDetailPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const originalInnerHeight = window.innerHeight
  let boundingRectSpy: ReturnType<typeof vi.spyOn> | null = null

  beforeEach(() => {
    apiRequestMock.mockReset()
    pushMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    clipboardWriteTextMock.mockReset()
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      writable: true,
      value: 900,
    })
    Object.assign(navigator, {
      clipboard: {
        writeText: clipboardWriteTextMock,
      },
    })
  })

  afterEach(() => {
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      writable: true,
      value: originalInnerHeight,
    })
    boundingRectSpy?.mockRestore()
    boundingRectSpy = null
    vi.clearAllMocks()
  })

  it("loads workflow details, supports copy id, and navigates back", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        return {
          data: {
            id: "workflow-123",
            name: "viral-mini-nf",
            source: "nf-core",
            engine: "nextflow",
            version: "2.0.0",
            description: "viral workflow",
            source_ref: "nf-core/viral-mini-nf",
            schema_json: null,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-123/dag") {
        return {
          data: {
            nodes: [{ id: "n1" }],
            edges: [],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowDetailPage />)

    expect(
      await screen.findByRole("heading", { name: "nf-core/viral-mini-nf" })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "workflows.detail.tabs.dag" }))
    expect(screen.getByTestId("dag-panel")).toHaveTextContent("workflow-123:1")

    fireEvent.click(screen.getByTitle("workflows.detail.copyId"))

    await waitFor(() => {
      expect(clipboardWriteTextMock).toHaveBeenCalledWith("workflow-123")
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("workflows.detail.toasts.copiedId")

    fireEvent.click(screen.getByRole("button", { name: "common.back" }))
    expect(pushMock).toHaveBeenCalledWith("/workflows")
  })

  it("sizes the workflow DAG viewport to the remaining screen height", async () => {
    boundingRectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 220,
      top: 220,
      left: 0,
      right: 0,
      bottom: 220,
      width: 0,
      height: 0,
      toJSON: () => ({}),
    })

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        return {
          data: {
            id: "workflow-123",
            name: "viral-mini-nf",
            source: "nf-core",
            engine: "nextflow",
            version: "2.0.0",
            description: "viral workflow",
            source_ref: "nf-core/viral-mini-nf",
            schema_json: null,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-123/dag") {
        return {
          data: {
            nodes: [{ id: "n1" }],
            edges: [],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowDetailPage />)

    expect(
      await screen.findByRole("heading", { name: "nf-core/viral-mini-nf" })
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole("tab", { name: "workflows.detail.tabs.dag" }))

    const dagFrame = screen.getByTestId("dag-panel").parentElement

    await waitFor(() => {
      expect(dagFrame).toHaveStyle({ minHeight: "400px" })
    })
  })

  it("shows the not-found fallback and keeps navigation available", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        throw new ApiError("workflow missing", 404, "NOT_FOUND")
      }
      if (path === "/workflows/workflow-123/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowDetailPage />)

    expect(
      await screen.findByText("workflows.detail.notFound.title")
    ).toBeInTheDocument()
    expect(toastErrorMock).toHaveBeenCalledWith("workflow missing")

    fireEvent.click(
      screen.getByRole("button", { name: "workflows.detail.backToWorkflows" })
    )
    expect(pushMock).toHaveBeenCalledWith("/workflows")
  })

  it("lazy-loads source only for local workflows", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        return {
          data: {
            id: "workflow-123",
            name: "local-flow",
            source: "local",
            engine: "nextflow",
            version: "1.0.0",
            description: "local workflow",
            source_ref: "local",
            entrypoint_relpath: "main.nf",
            schema_json: null,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-123/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/workflows/workflow-123/source") {
        return {
          data: { content: "process ALIGN\nworkflow { ALIGN() }" },
          meta: undefined,
        }
      }
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "workflow-123",
              name: "local-flow",
              source: "local",
              engine: "nextflow",
              version: "1.0.0",
              description: "local workflow",
              source_ref: "local",
              entrypoint_relpath: "main.nf",
              schema_json: null,
            },
            {
              id: "workflow-456",
              name: "local-flow",
              source: "local",
              engine: "nextflow",
              version: "0.9.0",
              description: "older local workflow",
              source_ref: "local",
              entrypoint_relpath: "main.nf",
              schema_json: null,
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-456/source") {
        return {
          data: { content: "process ALIGN\nprocess QC\nworkflow { QC(); ALIGN() }" },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const firstRender = renderAppPage(<WorkflowDetailPage />)

    expect(
      await screen.findByRole("heading", { name: "local-flow" })
    ).toBeInTheDocument()
    expect(
      apiRequestMock.mock.calls.some(([path]) => path === "/workflows/workflow-123/source")
    ).toBe(false)

    fireEvent.click(screen.getByRole("tab", { name: "workflows.detail.tabs.source" }))

    expect(await screen.findByTestId("source-tab")).toHaveTextContent(
      "local:process ALIGN workflow { ALIGN() }"
    )
    expect(screen.getByTestId("source-tab")).toHaveTextContent("compare-count:1")
    expect(
      apiRequestMock.mock.calls.some(([path]) => path === "/workflows")
    ).toBe(true)

    fireEvent.click(screen.getByRole("button", { name: "mock-compare-select" }))

    await waitFor(() => {
      expect(screen.getByTestId("source-tab")).toHaveTextContent(
        "compare-selected:workflow-456"
      )
    })
    await waitFor(() => {
      expect(screen.getByTestId("source-tab")).toHaveTextContent(
        "compare-source:process ALIGN process QC workflow { QC(); ALIGN() }"
      )
    })

    apiRequestMock.mockReset()
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        return {
          data: {
            id: "workflow-123",
            name: "viral-mini-nf",
            source: "nf-core",
            engine: "nextflow",
            version: "2.0.0",
            description: "hub workflow",
            source_ref: "nf-core/viral-mini-nf",
            schema_json: null,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-123/dag") {
        return { data: { nodes: [], edges: [] }, meta: undefined }
      }
      if (path === "/workflows/workflow-123/source") {
        throw new Error("should not load source for non-local workflow")
      }
      if (path === "/workflows") {
        throw new Error("should not load compare candidates for non-local workflow")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    firstRender.unmount()

    renderAppPage(<WorkflowDetailPage />)

    expect(
      await screen.findByRole("heading", { name: "nf-core/viral-mini-nf" })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "workflows.detail.tabs.source" }))

    expect(await screen.findByTestId("source-tab")).toHaveTextContent("nf-core:empty")
    expect(
      apiRequestMock.mock.calls.some(([path]) => path === "/workflows/workflow-123/source")
    ).toBe(false)
  })

  it("surfaces readiness guidance without legacy catalog badges", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        return {
          data: {
            id: "workflow-123",
            name: "Deaf_20",
            source: "local",
            engine: "wdl",
            version: "2.0.9.9",
            description: "Imported clinical workflow",
            source_ref: "local",
            entrypoint_relpath: "Deaf_20.wdl",
            schema_json: {
              workflow_name: "Deaf_20",
              version: "1.0",
              description: "Imported clinical workflow",
              inputs: [
                { name: "outdir", type: "String", optional: false, default: null, description: null },
                { name: "sequence_list", type: "File", optional: false, default: null, description: null },
              ],
              outputs: [],
              tasks: [
                { name: "PREPARATION", inputs: [], outputs: [], container: "deaf:2.0.9.9" },
                { name: "SPLIT", inputs: [], outputs: [], container: "deaf:2.0.9.9" },
                { name: "FILTER", inputs: [], outputs: [], container: "deaf:2.0.9.9" },
                { name: "ALIGN", inputs: [], outputs: [], container: "deaf:2.0.9.9" },
                { name: "RESULT", inputs: [], outputs: [], container: "deaf:2.0.9.9" },
              ],
              dependencies: [
                { source: "PREPARATION", target: "SPLIT" },
                { source: "PREPARATION", target: "FILTER" },
                { source: "SPLIT", target: "FILTER" },
                { source: "FILTER", target: "ALIGN" },
                { source: "ALIGN", target: "RESULT" },
              ],
            },
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-123/dag") {
        return {
          data: {
            nodes: [{ id: "a" }, { id: "b" }, { id: "c" }, { id: "d" }, { id: "e" }],
            edges: [{ id: "1" }, { id: "2" }, { id: "3" }, { id: "4" }, { id: "5" }],
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowDetailPage />)

    expect(await screen.findByRole("heading", { name: "Deaf_20" })).toBeInTheDocument()
    expect(screen.queryByText("workflows.detail.badges.starter")).not.toBeInTheDocument()
    expect(screen.getByText("workflows.detail.readiness.tasksCompact:5")).toBeInTheDocument()
    expect(screen.getByText("workflows.detail.readiness.dependenciesCompact:5")).toBeInTheDocument()
    expect(screen.getByText("workflows.detail.readiness.runtimeAssetsCompact")).toBeInTheDocument()
  })

  it("degrades gracefully when dag or source loading fails", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows/workflow-123") {
        return {
          data: {
            id: "workflow-123",
            name: "local-flow",
            source: "local",
            engine: "nextflow",
            version: "1.0.0",
            description: "local workflow",
            source_ref: "local",
            entrypoint_relpath: "main.nf",
            schema_json: null,
          },
          meta: undefined,
        }
      }
      if (path === "/workflows/workflow-123/dag") {
        throw new ApiError("dag unavailable", 404, "FILE_NOT_FOUND")
      }
      if (path === "/workflows/workflow-123/source") {
        throw new ApiError("source unavailable", 404, "FILE_NOT_FOUND")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowDetailPage />)

    expect(
      await screen.findByRole("heading", { name: "local-flow" })
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "workflows.detail.tabs.dag" }))
    expect(screen.getByTestId("dag-panel")).toHaveTextContent("workflow-123:0")

    fireEvent.click(screen.getByRole("tab", { name: "workflows.detail.tabs.source" }))

    expect(await screen.findByTestId("source-tab")).toHaveTextContent("local:empty")
    expect(toastErrorMock).not.toHaveBeenCalled()
  })
})
