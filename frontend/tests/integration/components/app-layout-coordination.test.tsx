import * as React from "react"
import { fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AppLayout from "@/app/(app)/app-layout"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useBreadcrumbDetail } from "@/components/bioinfoflow/breadcrumb-context"
import { useTerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock-context"
import { renderAppPage } from "@/tests/app-test-utils"

const pathnameState = {
  value: "/agent",
}

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameState.value,
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

describe("AppLayout coordination", () => {
  beforeEach(() => {
    pathnameState.value = "/agent"
    localStorage.clear()
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
})
