import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import WorkflowsPage from "@/app/(app)/workflows/page"
import { ApiError, apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const { pushMock, replaceMock, toastErrorMock, toastSuccessMock, toastInfoMock, toastWarningMock } =
  vi.hoisted(() => ({
    pushMock: vi.fn(),
    replaceMock: vi.fn(),
    toastErrorMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastInfoMock: vi.fn(),
    toastWarningMock: vi.fn(),
  }))

const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()
const searchParamsState = {
  scope: null as "hub" | "project" | null,
}

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  useSearchParams: () => ({
    get: (key: string) => {
      if (key === "scope") return searchParamsState.scope
      return null
    },
    toString: () => {
      const params = new URLSearchParams()
      if (searchParamsState.scope) params.set("scope", searchParamsState.scope)
      return params.toString()
    },
  }),
  usePathname: () => "/workflows",
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
    info: toastInfoMock,
    warning: toastWarningMock,
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

vi.mock("@/app/(app)/workflows/components/workflows-skeleton", () => ({
  WorkflowsGridSkeleton: () => <div data-testid="workflows-grid-skeleton" />,
  WorkflowsTableSkeleton: () => <div data-testid="workflows-table-skeleton" />,
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
    TabsList: ({ children }: { children: React.ReactNode }) => (
      <div>{children}</div>
    ),
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

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
    className,
  }: {
    children: React.ReactNode
    onClick?: () => void
    className?: string
  }) => (
    <button className={className} onClick={onClick}>
      {children}
    </button>
  ),
}))

vi.mock("@/components/ui/select", () => {
  const SelectContext = React.createContext<{
    value: string
    onValueChange: (value: string) => void
  } | null>(null)

  return {
    Select: ({
      value,
      onValueChange,
      children,
    }: {
      value: string
      onValueChange: (value: string) => void
      children: React.ReactNode
    }) => (
      <SelectContext.Provider value={{ value, onValueChange }}>
        <div>{children}</div>
      </SelectContext.Provider>
    ),
    SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
    SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectItem: ({
      value,
      children,
    }: {
      value: string
      children: React.ReactNode
    }) => {
      const context = React.useContext(SelectContext)
      return (
        <button
          type="button"
          aria-label={`select:${value}`}
          onClick={() => context?.onValueChange(value)}
        >
          {children}
        </button>
      )
    },
  }
})

vi.mock("@/app/(app)/workflows/components/workflow-register-dialog", () => ({
  WorkflowRegisterDialog: ({
    open,
    onOpenChange,
    onRegistered,
  }: {
    open: boolean
    onOpenChange: (open: boolean) => void
    onRegistered: (workflow: { id: string; name: string }) => void
  }) =>
    open ? (
      <div data-testid="workflow-register-dialog">
        <button
          onClick={() =>
            onRegistered({
              id: "new-wf-id",
              name: "test-workflow",
            })
          }
        >
          submit register
        </button>
        <button onClick={() => onOpenChange(false)}>close register</button>
      </div>
    ) : null,
}))

vi.mock("@/app/(app)/workflows/components/run-wizard-dialog", () => ({
  RunWizardDialog: ({
    open,
    workflow,
  }: {
    open: boolean
    workflow: { name: string } | null
  }) => (open ? <div data-testid="run-wizard-dialog">run:{workflow?.name}</div> : null),
}))

vi.mock("@/app/(app)/workflows/components/run-submission-wizard", () => ({
  RunSubmissionWizard: ({
    open,
    initialWorkflowId,
    availableWorkflows,
  }: {
    open: boolean
    initialWorkflowId?: string | null
    availableWorkflows?: Array<{ id: string; name: string }>
  }) =>
    open ? (
      <div data-testid="run-wizard-dialog">
        run:{availableWorkflows?.find((workflow) => workflow.id === initialWorkflowId)?.name ?? initialWorkflowId}
      </div>
    ) : null,
}))

describe("WorkflowsPage - project actions", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
    pushMock.mockReset()
    replaceMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    toastInfoMock.mockReset()
    toastWarningMock.mockReset()
    searchParamsState.scope = null
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("unbinds a project workflow group and refreshes the project list", async () => {
    let projectFetchCount = 0

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects/project-4/workflows") {
        projectFetchCount += 1
        return {
          data:
            projectFetchCount === 1
              ? [
                  {
                    source: "nf-core",
                    name: "viral-mini-nf",
                    pinned_workflow: {
                      id: "wf-project-a",
                      name: "viral-mini-nf",
                      description: "Project workflow",
                      source: "nf-core",
                      engine: "nextflow",
                      version: "1.0.0",
                      updated_at: "2026-03-16T00:00:00Z",
                    },
                    versions: [
                      {
                        id: "wf-project-a",
                        name: "viral-mini-nf",
                        description: "Project workflow",
                        source: "nf-core",
                        engine: "nextflow",
                        version: "1.0.0",
                        updated_at: "2026-03-16T00:00:00Z",
                      },
                      {
                        id: "wf-project-b",
                        name: "viral-mini-nf",
                        description: "Project workflow",
                        source: "nf-core",
                        engine: "nextflow",
                        version: "2.0.0",
                        updated_at: "2026-03-16T00:00:00Z",
                      },
                    ],
                  },
                ]
              : [],
          meta: undefined,
        }
      }
      if (
        (path === "/projects/project-4/workflows/wf-project-a:unbind" ||
          path === "/projects/project-4/workflows/wf-project-b:unbind") &&
        options?.method === "DELETE"
      ) {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-4" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.list" }))
    fireEvent.click(await screen.findByRole("button", { name: "workflows.actions.remove" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/projects/project-4/workflows/wf-project-a:unbind",
        { method: "DELETE" }
      )
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/projects/project-4/workflows/wf-project-b:unbind",
        { method: "DELETE" }
      )
    })
    expect(await screen.findByText("workflows.emptyProject")).toBeInTheDocument()
    expect(toastSuccessMock).toHaveBeenCalledWith(
      "workflows.toasts.removedFromProject:nf-core/viral-mini-nf"
    )
  })

  it("shows an error toast when unbinding a project workflow group fails", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects/project-5/workflows") {
        return {
          data: [
            {
              source: "nf-core",
              name: "viral-mini-nf",
              pinned_workflow: {
                id: "wf-project-c",
                name: "viral-mini-nf",
                description: "Project workflow",
                source: "nf-core",
                engine: "nextflow",
                version: "1.0.0",
                updated_at: "2026-03-16T00:00:00Z",
              },
              versions: [
                {
                  id: "wf-project-c",
                  name: "viral-mini-nf",
                  description: "Project workflow",
                  source: "nf-core",
                  engine: "nextflow",
                  version: "1.0.0",
                  updated_at: "2026-03-16T00:00:00Z",
                },
              ],
            },
          ],
          meta: undefined,
        }
      }
      if (
        path === "/projects/project-5/workflows/wf-project-c:unbind" &&
        options?.method === "DELETE"
      ) {
        throw new ApiError("Unbind failed")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-5" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.list" }))
    fireEvent.click(await screen.findByRole("button", { name: "workflows.actions.remove" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Unbind failed")
    })
  })

  it("pins a different workflow version and refreshes the project workflow group", async () => {
    let projectFetchCount = 0

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects/project-6/workflows") {
        projectFetchCount += 1
        return {
          data: [
            {
              source: "nf-core",
              name: "viral-mini-nf",
              pinned_workflow:
                projectFetchCount === 1
                  ? {
                      id: "wf-project-v1",
                      name: "viral-mini-nf",
                      description: "Project workflow",
                      source: "nf-core",
                      engine: "nextflow",
                      version: "1.0.0",
                      updated_at: "2026-03-16T00:00:00Z",
                    }
                  : {
                      id: "wf-project-v2",
                      name: "viral-mini-nf",
                      description: "Project workflow",
                      source: "nf-core",
                      engine: "nextflow",
                      version: "2.0.0",
                      updated_at: "2026-03-17T00:00:00Z",
                    },
              versions: [
                {
                  id: "wf-project-v1",
                  name: "viral-mini-nf",
                  description: "Project workflow",
                  source: "nf-core",
                  engine: "nextflow",
                  version: "1.0.0",
                  updated_at: "2026-03-16T00:00:00Z",
                },
                {
                  id: "wf-project-v2",
                  name: "viral-mini-nf",
                  description: "Project workflow",
                  source: "nf-core",
                  engine: "nextflow",
                  version: "2.0.0",
                  updated_at: "2026-03-17T00:00:00Z",
                },
              ],
            },
          ],
          meta: undefined,
        }
      }
      if (
        path === "/projects/project-6/workflow-pins" &&
        options?.method === "POST"
      ) {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-6" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.list" }))
    fireEvent.click(await screen.findByRole("button", { name: "select:wf-project-v2" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/projects/project-6/workflow-pins",
        {
          method: "POST",
          body: JSON.stringify({ pinned_workflow_id: "wf-project-v2" }),
        }
      )
    })
    await waitFor(() => {
      expect(
        apiRequestMock.mock.calls.filter(([path]) => path === "/projects/project-6/workflows")
      ).toHaveLength(2)
    })
  })

  it("shows an error toast when pinning a workflow version fails", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects/project-7/workflows") {
        return {
          data: [
            {
              source: "nf-core",
              name: "viral-mini-nf",
              pinned_workflow: {
                id: "wf-project-v1",
                name: "viral-mini-nf",
                description: "Project workflow",
                source: "nf-core",
                engine: "nextflow",
                version: "1.0.0",
                updated_at: "2026-03-16T00:00:00Z",
              },
              versions: [
                {
                  id: "wf-project-v1",
                  name: "viral-mini-nf",
                  description: "Project workflow",
                  source: "nf-core",
                  engine: "nextflow",
                  version: "1.0.0",
                  updated_at: "2026-03-16T00:00:00Z",
                },
                {
                  id: "wf-project-v2",
                  name: "viral-mini-nf",
                  description: "Project workflow",
                  source: "nf-core",
                  engine: "nextflow",
                  version: "2.0.0",
                  updated_at: "2026-03-17T00:00:00Z",
                },
              ],
            },
          ],
          meta: undefined,
        }
      }
      if (
        path === "/projects/project-7/workflow-pins" &&
        options?.method === "POST"
      ) {
        throw new ApiError("Pin failed")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-7" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.list" }))
    fireEvent.click(await screen.findByRole("button", { name: "select:wf-project-v2" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Pin failed")
    })
  })

  it("covers list-view hub actions and project run actions", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects/project-9/workflows") {
        return {
          data: [
            {
              source: "nf-core",
              name: "viral-mini-nf",
              pinned_workflow: {
                id: "wf-project-run",
                name: "viral-mini-nf",
                description: "Project workflow",
                source: "nf-core",
                engine: "nextflow",
                version: "1.0.0",
                updated_at: "2026-03-16T00:00:00Z",
              },
              versions: [
                {
                  id: "wf-project-run",
                  name: "viral-mini-nf",
                  description: "Project workflow",
                  source: "nf-core",
                  engine: "nextflow",
                  version: "1.0.0",
                  updated_at: "2026-03-16T00:00:00Z",
                },
              ],
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/workflows" && !options?.method) {
        return {
          data: [
            {
              id: "wf-hub-list-actions",
              name: "viral-mini-nf",
              description: "Hub workflow",
              source: "nf-core",
              engine: "nextflow",
              version: "2.0.0",
              updated_at: "2026-03-16T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-9" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.list" }))
    fireEvent.click(screen.getByRole("button", { name: "workflows.run" }))
    expect(screen.getByTestId("run-wizard-dialog")).toHaveTextContent("run:viral-mini-nf")

    fireEvent.click(screen.getByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByRole("table")).toBeInTheDocument()
    fireEvent.click(screen.getAllByText("workflows.viewDetails")[0])
    fireEvent.click(screen.getAllByText("workflows.editParameters")[0])
    fireEvent.click(screen.getAllByText("common.duplicate")[0])

    expect(pushMock).toHaveBeenCalledWith("/workflows/wf-hub-list-actions")
    expect(toastInfoMock).toHaveBeenCalledWith("workflows.toasts.parameterEditorTitle", {
      description: "workflows.toasts.parameterEditorDescription:viral-mini-nf",
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("common.duplicate", {
      description: "workflows.toasts.duplicatedDescription:viral-mini-nf",
    })
  })
})
