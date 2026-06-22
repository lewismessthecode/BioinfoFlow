import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import WorkflowsPage from "@/app/(app)/workflows/page"
import { apiRequest } from "@/lib/api"
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
    onRegistered: (workflow: {
      id: string
      name: string
      description: string
      source: string
      engine: string
      version: string
      updated_at: string
    }) => void
  }) =>
    open ? (
      <div data-testid="workflow-register-dialog">
        <button
          onClick={() =>
            onRegistered({
              id: "new-wf-id",
              name: "test-workflow",
              description: "New workflow",
              source: "local",
              engine: "wdl",
              version: "1.0.0",
              updated_at: "2026-05-28T00:00:00Z",
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
  }: {
    open: boolean
  }) => (open ? <div data-testid="run-wizard-dialog">run-open</div> : null),
}))

describe("WorkflowsPage - scope, search, and views", () => {
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

  it("shows the project empty state, then switches to hub workflows and filters search", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects/project-1/workflows") {
        return { data: [], meta: undefined }
      }
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-1",
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
      projectContext: { activeProjectId: "project-1" },
    })

    expect(await screen.findByText("workflows.emptyProject")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("common.search workflows.title"), {
      target: { value: "nomatch" },
    })
    expect(await screen.findByText("workflows.noWorkflows")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("common.search workflows.title"), {
      target: { value: "" },
    })
    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
  })

  it("prefers hub scope from the URL even when an active project exists", async () => {
    searchParamsState.scope = "hub"

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-url",
              name: "hub-default",
              description: "Hub workflow",
              source: "github",
              engine: "wdl",
              version: "2.1.0",
              updated_at: "2026-03-16T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/projects/project-url/workflows") {
        return {
          data: [],
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "project-url" },
    })

    expect(await screen.findByText("hub-default")).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "workflows.scopes.hub" })).toHaveAttribute(
      "aria-selected",
      "true"
    )
    expect(
      apiRequestMock.mock.calls.some(([path]) => path === "/projects/project-url/workflows")
    ).toBe(false)
  })

  it("shows hub workflows directly when catalog overlays are absent", async () => {
    searchParamsState.scope = "hub"

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

    expect(await screen.findByText("Deaf_20")).toBeInTheDocument()
    expect(screen.queryByText("BGI Deaf 20 Hearing Panel")).not.toBeInTheDocument()
  })

  it("toggles between cards and list views across project and hub scopes", async () => {
    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects/project-3/workflows") {
        return {
          data: [
            {
              source: "nf-core",
              name: "viral-mini-nf",
              pinned_workflow: {
                id: "wf-project-1",
                name: "viral-mini-nf",
                description: "Project workflow",
                source: "nf-core",
                engine: "nextflow",
                version: "1.0.0",
                updated_at: "2026-03-16T00:00:00Z",
              },
              versions: [
                {
                  id: "wf-project-1",
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
      if (path === "/workflows") {
        return {
          data: [
            {
              id: "wf-hub-4",
              name: "hub-pipeline",
              description: "Hub workflow",
              source: "github",
              engine: "wdl",
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
      projectContext: { activeProjectId: "project-3" },
    })

    expect(await screen.findByText("nf-core/viral-mini-nf")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.list" }))
    expect(await screen.findByRole("table")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("tab", { name: "workflows.scopes.hub" }))
    expect(await screen.findByText("hub-pipeline")).toBeInTheDocument()
    expect(screen.getByRole("table")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "workflows.viewModes.cards" }))
    await waitFor(() => {
      expect(screen.queryByRole("table")).not.toBeInTheDocument()
    })
    expect(screen.getByText("hub-pipeline")).toBeInTheDocument()
  })

  it("adds the registered workflow to the hub list when onRegistered fires", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows" && !options?.method) {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "" },
    })

    fireEvent.click(await screen.findByRole("button", { name: "workflows.register" }))
    expect(screen.getByTestId("workflow-register-dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByText("submit register"))

    await waitFor(() => {
      expect(screen.getByText("test-workflow")).toBeInTheDocument()
    })
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-workflow-registered")
  })

  it("celebrates workflow registration when the hub already has workflows", async () => {
    searchParamsState.scope = "hub"
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows" && !options?.method) {
        return {
          data: [
            {
              id: "existing-wf",
              name: "existing-workflow",
              description: "Already registered",
              source: "local",
              engine: "wdl",
              version: "1.0.0",
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

    expect(await screen.findByText("existing-workflow")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))
    fireEvent.click(screen.getByText("submit register"))

    await waitFor(() => {
      expect(screen.getByText("test-workflow")).toBeInTheDocument()
    })
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-workflow-registered")
  })

  it("closes the register dialog via onOpenChange", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/workflows" && !options?.method) {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    renderAppPage(<WorkflowsPage />, {
      projectContext: { activeProjectId: "" },
    })

    fireEvent.click(await screen.findByRole("button", { name: "workflows.register" }))
    expect(screen.getByTestId("workflow-register-dialog")).toBeInTheDocument()

    fireEvent.click(screen.getByText("close register"))
    expect(screen.queryByTestId("workflow-register-dialog")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "workflows.register" }))
    expect(screen.getByTestId("workflow-register-dialog")).toBeInTheDocument()
  })
})
