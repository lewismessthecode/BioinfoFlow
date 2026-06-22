import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import WorkflowsPage from "@/app/(app)/workflows/page"
import { ApiError, apiRequest } from "@/lib/api"
import { renderAppPage } from "@/tests/app-test-utils"

const { pushMock, replaceMock, toastErrorMock, toastSuccessMock, toastInfoMock, toastWarningMock, celebrateMilestoneMock } =
  vi.hoisted(() => ({
    pushMock: vi.fn(),
    replaceMock: vi.fn(),
    toastErrorMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastInfoMock: vi.fn(),
    toastWarningMock: vi.fn(),
    celebrateMilestoneMock: vi.fn(),
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

vi.mock("@/lib/celebrations", () => ({
  celebrateMilestone: (...args: unknown[]) => celebrateMilestoneMock(...args),
}))

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

describe("WorkflowsPage - hub actions", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  beforeEach(() => {
    apiRequestMock.mockReset()
    pushMock.mockReset()
    replaceMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    toastInfoMock.mockReset()
    toastWarningMock.mockReset()
    celebrateMilestoneMock.mockReset()
    searchParamsState.scope = null
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("binds a workflow and opens the run dialog from hub actions", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-2",
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
      if (
        path === "/projects/project-9/workflows/wf-hub-2:bind" &&
        options?.method === "POST"
      ) {
        return { data: null, meta: undefined }
      }
      if (path === "/projects/project-9/workflows") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-9" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()

    // Hub cards show "Add" which binds the workflow when a project is selected
    fireEvent.click(screen.getByRole("button", { name: "workflows.actions.add" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/projects/project-9/workflows/wf-hub-2:bind",
        { method: "POST" }
      )
    })
    expect(toastSuccessMock).toHaveBeenCalledWith(
      "workflows.toasts.addedToProject:nf-core/viral-mini-nf"
    )
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-workflow-bound")
  })

  it("does not celebrate binding when the project already has workflows", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-existing",
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
      if (path === "/projects/project-9/workflows") {
        return {
          data: [
            {
              source: "local",
              name: "already-bound",
              engine: "wdl",
              pinned_workflow: {
                id: "wf-existing",
                name: "already-bound",
                source: "local",
                engine: "wdl",
                version: "1.0.0",
                updated_at: "2026-03-16T00:00:00Z",
              },
              versions: [],
            },
          ],
          meta: undefined,
        }
      }
      if (
        path === "/projects/project-9/workflows/wf-hub-existing:bind" &&
        options?.method === "POST"
      ) {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-9" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "workflows.actions.add" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/projects/project-9/workflows/wf-hub-existing:bind",
        { method: "POST" }
      )
    })
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
  })

  it("shows an error toast when binding a workflow fails", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-3",
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
      if (
        path === "/projects/project-2/workflows/wf-hub-3:bind" &&
        options?.method === "POST"
      ) {
        throw new ApiError("Bind failed")
      }
      if (path === "/projects/project-2/workflows") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-2" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()

    fireEvent.click(await screen.findByRole("button", { name: "workflows.actions.add" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Bind failed")
    })
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
  })

  it("renders registered workflows without catalog overlays in hub scope", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-deaf20",
              name: "Deaf_20",
              description: "Imported clinical workflow",
              source: "local",
              engine: "wdl",
              version: "2.0.9.9",
              updated_at: "2026-03-20T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-market" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))

    expect((await screen.findAllByText("Deaf_20")).length).toBeGreaterThan(0)
    expect(screen.queryByText("BGI Deaf 20 Hearing Panel")).not.toBeInTheDocument()
  })

  it("groups same-name hub workflows into one card and shows the latest version", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-deaf20-v2099",
              name: "Deaf_20",
              description: "Older imported clinical workflow",
              source: "local",
              engine: "wdl",
              version: "V2.0.9.9",
              updated_at: "2026-03-20T00:00:00Z",
            },
            {
              id: "wf-deaf20-v2100",
              name: "Deaf_20",
              description: "Latest imported clinical workflow",
              source: "local",
              engine: "wdl",
              version: "V2.1.0.0",
              updated_at: "2026-03-21T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-market" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))

    expect(await screen.findByText("Deaf_20")).toBeInTheDocument()
    expect(screen.getAllByText("Deaf_20")).toHaveLength(1)
    // Selected version renders in the dropdown trigger (and may repeat inside
    // the menu when open), so assert presence rather than uniqueness.
    expect(screen.getAllByText("V2.1.0.0").length).toBeGreaterThan(0)
    expect(screen.getByText("workflows.versionCount:2")).toBeInTheDocument()
    // Older versions live inside the dropdown menu — they're reachable but
    // not promoted to the card surface.
    expect(
      screen.getByRole("button", { name: "select:wf-deaf20-v2099" }),
    ).toBeInTheDocument()
  })

  it("does not rewrite workflow names from removed catalog metadata", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-deaf20",
              name: "Deaf_20",
              description: "Imported clinical workflow",
              source: "local",
              engine: "wdl",
              version: "2.0.9.9",
              updated_at: "2026-03-20T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-market" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))

    expect(await screen.findByText("Deaf_20")).toBeInTheDocument()
    expect(screen.queryByText("BGI Deaf 20 Hearing Panel")).not.toBeInTheDocument()
  })

  it("shows delete actions for ordinary workflows when catalog metadata is gone", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-deaf20",
              name: "Deaf_20",
              description: "Imported clinical workflow",
              source: "local",
              engine: "wdl",
              version: "2.0.9.9",
              updated_at: "2026-03-20T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-market" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))

    expect((await screen.findAllByText("Deaf_20")).length).toBeGreaterThan(0)
    expect(screen.getByText("workflows.delete")).toBeInTheDocument()
  })

  it("does not open the run dialog when add and run fails to bind the workflow", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-5",
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
      if (
        path === "/projects/project-8/workflows/wf-hub-5:bind" &&
        options?.method === "POST"
      ) {
        throw new ApiError("Bind failed")
      }
      if (path === "/projects/project-8/workflows") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-8" },
    })

    fireEvent.click(await screen.findByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()

    // Hub cards now show Add + Details, not Run. Clicking Add triggers bind.
    fireEvent.click(screen.getByRole("button", { name: "workflows.actions.add" }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Bind failed")
    })
  })

  it("routes to details, opens parameter editor, duplicates, and deletes hub workflows", async () => {
    const deleteActions: Array<() => Promise<void>> = []

    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        deleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows" && !options?.method) {
        return {
          data: [
            {
              id: "wf-hub-actions",
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
      if (path === "/workflows/wf-hub-actions" && options?.method === "DELETE") {
        return { data: null, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()

    // viewDetails appears in both dropdown and card button — use getAllByText
    fireEvent.click(screen.getAllByText("workflows.viewDetails")[0])
    expect(pushMock).toHaveBeenCalledWith("/workflows/wf-hub-actions")

    fireEvent.click(screen.getByText("workflows.editParameters"))
    expect(toastInfoMock).toHaveBeenCalledWith("workflows.toasts.parameterEditorTitle", {
      description: "workflows.toasts.parameterEditorDescription:viral-mini-nf",
    })

    fireEvent.click(screen.getByText("common.duplicate"))
    expect(toastSuccessMock).toHaveBeenCalledWith("common.duplicate", {
      description: "workflows.toasts.duplicatedDescription:viral-mini-nf",
    })

    fireEvent.click(screen.getByText("workflows.delete"))
    expect(deleteActions).toHaveLength(1)
    await deleteActions[0]()

    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith("workflows.toasts.deleted:viral-mini-nf")
      expect(screen.getByText("workflows.noWorkflows")).toBeInTheDocument()
    })
  })

  it("shows an error toast when deleting a hub workflow fails", async () => {
    const deleteActions: Array<() => Promise<void>> = []

    toastWarningMock.mockImplementation((_message, options) => {
      if (options?.action?.onClick) {
        deleteActions.push(options.action.onClick)
      }
    })
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows" && !options?.method) {
        return {
          data: [
            {
              id: "wf-hub-delete",
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
      if (path === "/workflows/wf-hub-delete" && options?.method === "DELETE") {
        throw new ApiError("Delete failed")
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    fireEvent.click(screen.getByText("workflows.delete"))
    expect(deleteActions).toHaveLength(1)

    await deleteActions[0]()

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Delete failed")
    })
  })

  it("shows view details instead of add when no project is selected in hub", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows" && !options?.method) {
        return {
          data: [
            {
              id: "wf-hub-select-project",
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
      projectContext: { activeProjectId: "" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    // Without a project, the left button shows viewDetails instead of Add
    const viewDetailsButtons = screen.getAllByText("workflows.viewDetails")
    expect(viewDetailsButtons.length).toBeGreaterThanOrEqual(1)
  })
})
