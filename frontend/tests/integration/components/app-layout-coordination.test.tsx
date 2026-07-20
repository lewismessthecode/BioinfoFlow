import * as React from "react"
import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AppLayout from "@/app/(app)/app-layout"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useBreadcrumbDetail } from "@/components/bioinfoflow/breadcrumb-context"
import { useTerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock-context"
import { renderAppPage } from "@/tests/app-test-utils"
import { firstRunActivationStorageKey } from "@/lib/first-run"

const pathnameState = {
  value: "/agent",
}

const searchParamsState = {
  value: new URLSearchParams(),
}

const freshDemoResult = {
  ready: true,
  created: true,
  demo_project_id: "project-demo",
  workflow_id: "workflow-demo",
  starter_context: {
    project_id: "project-demo",
    workflow: {
      id: "workflow-demo",
      name: "bioinfoflow-quickstart",
      version: "1.0.0",
      source: "local",
      engine: "wdl",
      scope: "project" as const,
      project_id: "project-demo",
    },
    values: {
      samples_tsv: "asset://project/samples.tsv",
      sample_a_fastq: "asset://project/sample-a.fastq",
      sample_b_fastq: "asset://project/sample-b.fastq",
    },
  },
}
let firstRunStateMock: {
  data: typeof freshDemoResult | null
  isLoading: boolean
  error: Error | null
}

vi.mock("@/hooks/use-first-run", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/use-first-run")>(
    "@/hooks/use-first-run",
  )
  return {
    ...actual,
    useFirstRun: () => firstRunStateMock,
  }
})

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameState.value,
  useSearchParams: () => searchParamsState.value,
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
}))

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: React.PropsWithChildren<{ href: string } & React.AnchorHTMLAttributes<HTMLAnchorElement>>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("next/dynamic", () => ({
  default: () => {
    return function DynamicMock(props: Record<string, unknown>) {
      const { isOpen } = useTerminalDock()

      if ("open" in props) {
        return <div data-testid="command-palette-shell" />
      }

      return <div data-testid="terminal-dock">{isOpen ? "open" : "closed"}</div>
    }
  },
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const labels: Record<string, Record<string, string>> = {
      accessibility: {
        openTerminal: "Open terminal",
      },
      nav: {
        dashboard: "Dashboard",
        agent: "Agent",
        runs: "Runs",
      },
    }
    return labels[namespace]?.[key] ?? `${namespace}.${key}`
  },
}))

vi.mock("@/components/bioinfoflow/navbar", async () => {
  const { Breadcrumbs } = await vi.importActual<typeof import("@/components/bioinfoflow/breadcrumbs")>(
    "@/components/bioinfoflow/breadcrumbs",
  )

  return {
    Navbar: ({
      children,
      projectName,
      conversationTitle,
      onSidebarToggle,
    }: {
      children?: React.ReactNode
      projectName?: string
      conversationTitle?: string
      onSidebarToggle?: () => void
    }) => (
      <div>
        <button onClick={onSidebarToggle}>toggle navigation</button>
        <Breadcrumbs
          projectName={projectName}
          conversationTitle={conversationTitle}
        />
        <div data-testid="navbar-actions">{children}</div>
      </div>
    ),
  }
})

vi.mock("@/components/bioinfoflow/sidebar/index", () => ({
  Sidebar: ({ collapsed }: { collapsed: boolean }) => (
    <div data-testid="sidebar-state">{collapsed ? "collapsed" : "expanded"}</div>
  ),
  SettingsSidebar: ({ activeSection }: { activeSection: string }) => (
    <div data-testid="settings-sidebar-state">{activeSection}</div>
  ),
}))

vi.mock("@/components/bioinfoflow/sidebar/sidebar-drawer", () => ({
  SidebarDrawer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  WorkspaceShellProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useWorkspaceShell: () => ({ navbarActions: null }),
}))

vi.mock("@/components/bioinfoflow/command-palette", () => ({
  CommandPalette: () => null,
}))

vi.mock("@/components/ui/sonner", () => ({
  Toaster: () => null,
}))

vi.mock("@/components/ui/resize-handle", () => ({
  ResizeHandle: () => null,
}))

vi.mock("@/hooks/use-media-query", () => ({
  useIsMobile: () => false,
}))

vi.mock("@/components/bioinfoflow/terminal/terminal-dock", () => ({
  TerminalDock: () => {
    const { isOpen } = useTerminalDock()
    return <div data-testid="terminal-dock">{isOpen ? "open" : "closed"}</div>
  },
}))

function LayoutStateSeeder({
  projectId,
  projectName,
  conversationTitle,
  detail,
}: {
  projectId: string
  projectName: string
  conversationTitle?: string
  detail?: { label: string; href?: string } | null
}) {
  const {
    setActiveProjectId,
    setActiveProjectName,
    setActiveConversationTitle,
  } = useProjectContext()
  const { setDetail } = useBreadcrumbDetail()

  React.useEffect(() => {
    setActiveProjectId(projectId)
    setActiveProjectName(projectName)
    setActiveConversationTitle(conversationTitle ?? "")
    setDetail(detail ?? null)
  }, [
    conversationTitle,
    detail,
    projectId,
    projectName,
    setActiveConversationTitle,
    setActiveProjectId,
    setActiveProjectName,
    setDetail,
  ])

  return <div>page content</div>
}

function ProjectStateProbe() {
  const { selectedProjectId, conversationProjectId, selectWorkspaceProject } =
    useProjectContext()
  return (
    <div>
      <span data-testid="selected-project">{selectedProjectId || "none"}</span>
      <span data-testid="conversation-project">
        {conversationProjectId || "none"}
      </span>
      <button onClick={() => selectWorkspaceProject("")}>clear project</button>
    </div>
  )
}

describe("AppLayout coordination", () => {
  beforeEach(() => {
    pathnameState.value = "/agent"
    searchParamsState.value = new URLSearchParams()
    localStorage.clear()
    firstRunStateMock = { data: null, isLoading: false, error: null }
  })

  it("activates a freshly created demo exactly once", async () => {
    firstRunStateMock = {
      data: freshDemoResult,
      isLoading: false,
      error: null,
    }
    renderAppPage(
      <AppLayout>
        <ProjectStateProbe />
      </AppLayout>,
    )

    await waitFor(() =>
      expect(screen.getByTestId("selected-project")).toHaveTextContent(
        "project-demo",
      ),
    )
    expect(screen.getByTestId("conversation-project")).toHaveTextContent(
      "project-demo",
    )

    fireEvent.click(screen.getByRole("button", { name: "clear project" }))
    await waitFor(() =>
      expect(screen.getByTestId("selected-project")).toHaveTextContent("none"),
    )
    expect(screen.getByTestId("conversation-project")).toHaveTextContent("none")
  })

  it("does not mark the demo activated when deferred selection is cleaned up", () => {
    vi.useFakeTimers()
    try {
      firstRunStateMock = {
        data: freshDemoResult,
        isLoading: false,
        error: null,
      }
      const { unmount } = renderAppPage(
        <AppLayout>
          <ProjectStateProbe />
        </AppLayout>,
      )

      unmount()
      act(() => vi.runAllTimers())

      expect(
        localStorage.getItem(firstRunActivationStorageKey("project-demo")),
      ).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it("activates an existing demo after an interrupted first bootstrap response", async () => {
    vi.useFakeTimers()
    try {
      firstRunStateMock = {
        data: freshDemoResult,
        isLoading: false,
        error: null,
      }
      const firstRender = renderAppPage(
        <AppLayout>
          <ProjectStateProbe />
        </AppLayout>,
      )

      firstRender.unmount()
      act(() => vi.runAllTimers())
      expect(
        localStorage.getItem(firstRunActivationStorageKey("project-demo")),
      ).toBeNull()

      firstRunStateMock = {
        data: { ...freshDemoResult, created: false },
        isLoading: false,
        error: null,
      }
      renderAppPage(
        <AppLayout>
          <ProjectStateProbe />
        </AppLayout>,
      )
      act(() => vi.runAllTimers())

      expect(screen.getByTestId("selected-project")).toHaveTextContent(
        "project-demo",
      )
      expect(screen.getByTestId("conversation-project")).toHaveTextContent(
        "project-demo",
      )
      expect(
        localStorage.getItem(firstRunActivationStorageKey("project-demo")),
      ).toBe("true")
    } finally {
      vi.useRealTimers()
    }
  })

  it("does not replace a remembered project with the fresh demo", async () => {
    localStorage.setItem("bioinfoflow:last-used-project", "project-existing")
    firstRunStateMock = {
      data: freshDemoResult,
      isLoading: false,
      error: null,
    }
    renderAppPage(
      <AppLayout>
        <ProjectStateProbe />
      </AppLayout>,
    )

    await waitFor(() =>
      expect(screen.getByTestId("selected-project")).toHaveTextContent("none"),
    )
    expect(screen.getByTestId("conversation-project")).toHaveTextContent("none")
  })

  it("does not replace an existing project selected before bootstrap completes", async () => {
    const { rerender } = renderAppPage(
      <AppLayout>
        <LayoutStateSeeder projectId="project-existing" projectName="Existing" />
        <ProjectStateProbe />
      </AppLayout>,
    )
    expect(await screen.findByTestId("selected-project")).toHaveTextContent(
      "project-existing",
    )

    firstRunStateMock = {
      data: freshDemoResult,
      isLoading: false,
      error: null,
    }
    rerender(
      <AppLayout>
        <LayoutStateSeeder projectId="project-existing" projectName="Existing" />
        <ProjectStateProbe />
      </AppLayout>,
    )

    await waitFor(() =>
      expect(screen.getByTestId("selected-project")).toHaveTextContent(
        "project-existing",
      ),
    )
    expect(screen.getByTestId("conversation-project")).toHaveTextContent(
      "project-existing",
    )
  })

  it("keeps breadcrumbs, the left sidebar, and the terminal dock coordinated on terminal-enabled routes", async () => {
    renderAppPage(
      <AppLayout>
        <LayoutStateSeeder
          projectId="project-1"
          projectName="Cancer Cohort"
          conversationTitle="Initial analysis"
        />
      </AppLayout>,
    )

    expect(await screen.findByText("Cancer Cohort")).toBeInTheDocument()
    expect(screen.getByText("Initial analysis")).toBeInTheDocument()
    expect(screen.getByTestId("sidebar-state")).toHaveTextContent("expanded")
    expect(screen.getByTestId("terminal-dock")).toHaveTextContent("closed")

    fireEvent.click(screen.getByRole("button", { name: "Open terminal" }))
    await waitFor(() => {
      expect(screen.getByTestId("terminal-dock")).toHaveTextContent("open")
    })

    fireEvent.keyDown(window, { key: "b", ctrlKey: true })
    await waitFor(() => {
      expect(screen.getByTestId("sidebar-state")).toHaveTextContent("collapsed")
      expect(localStorage.getItem("left-sidebar-collapsed")).toBe("true")
    })
  })

  it("updates breadcrumbs and terminal affordances when the route changes under the same layout shell", async () => {
    pathnameState.value = "/runs/run-1"

    const { rerender } = renderAppPage(
      <AppLayout>
        <LayoutStateSeeder
          projectId="project-1"
          projectName="Cancer Cohort"
          detail={{ label: "Run r-123", href: "/runs/run-1" }}
        />
      </AppLayout>,
    )

    expect(await screen.findByText("Cancer Cohort")).toBeInTheDocument()
    expect(screen.getByText("Runs")).toBeInTheDocument()
    expect(screen.getByText("Run r-123")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open terminal" })).toBeInTheDocument()

    pathnameState.value = "/dashboard"
    rerender(
      <AppLayout>
        <LayoutStateSeeder
          projectId="project-1"
          projectName="Cancer Cohort"
          detail={null}
        />
      </AppLayout>,
    )

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Open terminal" })).not.toBeInTheDocument()
    })
    expect(screen.getByText("Dashboard")).toBeInTheDocument()
    expect(screen.queryByText("Run r-123")).not.toBeInTheDocument()
  })

  it("renders the settings sidebar instead of the workspace sidebar on settings routes", async () => {
    pathnameState.value = "/settings"
    searchParamsState.value = new URLSearchParams("section=appearance")

    renderAppPage(
      <AppLayout>
        <LayoutStateSeeder projectId="project-1" projectName="Cancer Cohort" />
      </AppLayout>,
    )

    expect(await screen.findByTestId("settings-sidebar-state")).toHaveTextContent("appearance")
    expect(screen.queryByTestId("sidebar-state")).not.toBeInTheDocument()
  })
})
