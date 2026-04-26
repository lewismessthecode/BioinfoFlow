import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import WorkflowsPage from "@/app/(app)/workflows/page"
import { createDemoRuntime, setActiveRuntimeForTests } from "@/lib/runtime"
import { renderAppPage } from "@/tests/app-test-utils"

const routerPushMock = vi.fn()
const routerReplaceMock = vi.fn()
const translationMocks = new Map<
  string,
  (key: string, values?: Record<string, unknown>) => string
>()

const searchParamsState = {
  scope: null as "hub" | "project" | null,
}

let demoRuntime: ReturnType<typeof createDemoRuntime>

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPushMock, replace: routerReplaceMock }),
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
        },
      )
    }

    return translationMocks.get(namespace)!
  },
}))

vi.mock("next/dynamic", () => ({
  default: (
    loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>,
  ) => {
    return function DynamicMock(props: Record<string, unknown>) {
      const [Component, setComponent] =
        React.useState<React.ComponentType<Record<string, unknown>> | null>(null)

      React.useEffect(() => {
        let cancelled = false

        const load = async () => {
          const loaded = await loader()
          if (!cancelled) {
            setComponent(() => loaded.default)
          }
        }

        void load()

        return () => {
          cancelled = true
        }
      }, [])

      return Component ? <Component {...props} /> : null
    }
  },
}))

vi.mock("@/app/(app)/workflows/components/workflows-skeleton", () => ({
  WorkflowsGridSkeleton: () => <div data-testid="workflows-grid-skeleton" />,
  WorkflowsTableSkeleton: () => <div data-testid="workflows-table-skeleton" />,
}))

vi.mock("@/app/(app)/workflows/components/workflow-register-dialog", () => ({
  WorkflowRegisterDialog: () => null,
}))

vi.mock("@/app/(app)/workflows/components/project-group-card", () => ({
  ProjectGroupCard: ({
    group,
    onRun,
  }: {
    group: { pinned_workflow: { id: string; name: string } }
    onRun: (workflow: { id: string; name: string }) => void
  }) => (
    <div data-testid={`project-group-${group.pinned_workflow.id}`}>
      <div>{group.pinned_workflow.name}</div>
      <button onClick={() => onRun(group.pinned_workflow)}>workflows.run</button>
    </div>
  ),
}))

vi.mock("@/app/(app)/workflows/components/hub-workflow-card", () => ({
  HubWorkflowCard: ({ group }: { group: { name: string } }) => (
    <div>{group.name}</div>
  ),
}))

vi.mock("@/app/(app)/workflows/components/workflow-table-views", () => ({
  HubWorkflowsTable: () => null,
  ProjectWorkflowsTable: () => null,
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
      children,
      disabled,
    }: {
      value: string
      children: React.ReactNode
      disabled?: boolean
    }) => {
      const context = React.useContext(TabsContext)
      return (
        <button
          disabled={disabled}
          onClick={() => context?.onValueChange(value)}
          role="tab"
        >
          {children}
        </button>
      )
    },
  }
})

vi.mock("@/app/(app)/workflows/components/run-submission-wizard", () => ({
  RunSubmissionWizard: ({
    open,
    projectId,
    initialWorkflowId,
    onSubmitted,
  }: {
    open: boolean
    projectId: string
    initialWorkflowId?: string | null
    onSubmitted?: (runId: string) => void
  }) => {
    if (!open || !initialWorkflowId) return null

    return (
      <button
        onClick={async () => {
          const response = await demoRuntime.request<{ run_id: string }>("/runs", {
            method: "POST",
            body: JSON.stringify({
              project_id: projectId,
              workflow_id: initialWorkflowId,
              values: {
                reads_r1: "deliveries/ecoli_R1.fastq.gz",
                reads_r2: "deliveries/ecoli_R2.fastq.gz",
                reference: "reference/ecoli_k12.fa",
              },
            }),
          })
          onSubmitted?.(response.data.run_id)
        }}
      >
        submit demo workflow
      </button>
    )
  },
}))

describe("WorkflowsPage under demo runtime", () => {
  beforeEach(() => {
    vi.stubEnv("APP_RUNTIME", "demo")
    vi.stubEnv("DEPLOY_MODE", "demo")
    demoRuntime = createDemoRuntime()
    setActiveRuntimeForTests(demoRuntime)
    routerPushMock.mockReset()
    routerReplaceMock.mockReset()
    searchParamsState.scope = null
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    setActiveRuntimeForTests(null)
  })

  it(
    "renders the seeded project workflow and navigates to runs after a simulated submit",
    async () => {
      renderAppPage(<WorkflowsPage />, {
        projectContext: {
          activeProjectId: "project-demo",
          selectedProjectId: "project-demo",
          conversationProjectId: "project-demo",
        },
      })

      expect(
        await screen.findByTestId("project-group-wf-rnaseq-quant-mini"),
      ).toHaveTextContent("rnaseq-quant-mini")

      fireEvent.click(screen.getByRole("button", { name: "workflows.run" }))
      fireEvent.click(await screen.findByRole("button", { name: "submit demo workflow" }))

      await waitFor(() => {
        expect(routerPushMock).toHaveBeenCalledWith(
          "/runs?highlight=run_demo_001&scope=project&project_id=project-demo",
        )
      })
    },
    10000,
  )
})
