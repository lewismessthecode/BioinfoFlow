import * as React from "react"
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AppLayout from "@/app/(app)/app-layout"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useTerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock-context"
import { renderAppPage } from "@/tests/app-test-utils"

const pathnameState = {
  value: "/agent",
}

const searchParamsState = {
  value: new URLSearchParams(),
}

let workspaceNavbarActions: React.ReactNode = null

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameState.value,
  useSearchParams: () => searchParamsState.value,
}))

vi.mock("next/dynamic", () => ({
  default: () => {
    return function DynamicMock(props: Record<string, unknown>) {
      const { isOpen } = useTerminalDock()

      if ("open" in props) {
        return (
          <div data-testid="command-palette-shell">
            {props.open ? "open" : "closed"}
          </div>
        )
      }

      return <div data-testid="terminal-dock">{isOpen ? "open" : "closed"}</div>
    }
  },
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))

vi.mock("@/components/bioinfoflow/navbar", () => ({
  Navbar: ({ children }: { children?: React.ReactNode }) => (
    <div>
      <div>navbar</div>
      <div data-testid="navbar-actions">{children}</div>
    </div>
  ),
}))

vi.mock("@/components/bioinfoflow/sidebar/index", () => ({
  Sidebar: () => <div>sidebar</div>,
  SettingsSidebar: () => <div>settings sidebar</div>,
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  WorkspaceShellProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useWorkspaceShell: () => ({ navbarActions: workspaceNavbarActions }),
}))

vi.mock("@/components/bioinfoflow/sidebar/sidebar-drawer", () => ({
  SidebarDrawer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock("@/components/bioinfoflow/command-palette", () => ({
  CommandPalette: ({ open }: { open: boolean }) => (
    <div data-testid="command-palette-shell">
      {open ? "open" : "closed"}
    </div>
  ),
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

function ProjectSeeder({ projectId }: { projectId: string }) {
  const { setActiveProjectId } = useProjectContext()

  React.useEffect(() => {
    setActiveProjectId(projectId)
  }, [projectId, setActiveProjectId])

  return <div>page</div>
}

describe("AppLayout terminal integration", () => {
  beforeEach(() => {
    workspaceNavbarActions = null
    searchParamsState.value = new URLSearchParams()
    localStorage.clear()
  })

  it("shows the terminal toggle on terminal-enabled routes when a project is active", async () => {
    pathnameState.value = "/agent"

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "accessibility.openTerminal" })).toBeInTheDocument()
    })
  })

  it("opens the terminal dock when the navbar action is clicked", async () => {
    pathnameState.value = "/agent"

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    const toggle = await screen.findByRole("button", { name: "accessibility.openTerminal" })
    expect(screen.getByTestId("terminal-dock")).toHaveTextContent("closed")

    fireEvent.click(toggle)

    await waitFor(() => {
      expect(screen.getByTestId("terminal-dock")).toHaveTextContent("open")
    })
  })

  it("does not restore a previously open terminal dock automatically", async () => {
    pathnameState.value = "/agent"
    localStorage.setItem("terminal-dock:project-1:open", "true")

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    await screen.findByRole("button", { name: "accessibility.openTerminal" })
    expect(screen.getByTestId("terminal-dock")).toHaveTextContent("closed")
    expect(localStorage.getItem("terminal-dock:project-1:open")).toBeNull()
  })

  it("does not open the terminal dock from the old keyboard shortcut", async () => {
    pathnameState.value = "/agent"

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    await screen.findByRole("button", { name: "accessibility.openTerminal" })
    fireEvent.keyDown(window, { key: "j", metaKey: true })

    expect(screen.getByTestId("terminal-dock")).toHaveTextContent("closed")
  })

  it("keeps the right-side panel toggle as the far-right navbar action", async () => {
    pathnameState.value = "/agent"
    workspaceNavbarActions = (
      <button type="button" aria-label="Open run panel">
        drawer
      </button>
    )

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "accessibility.openTerminal" })).toBeInTheDocument()
    })

    const buttons = within(screen.getByTestId("navbar-actions")).getAllByRole("button")
    expect(buttons.map((button) => button.getAttribute("aria-label"))).toEqual([
      "accessibility.openTerminal",
      "Open run panel",
    ])
  })

  it("does not mount the command palette until the shortcut is used", async () => {
    pathnameState.value = "/agent"

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    expect(screen.queryByTestId("command-palette-shell")).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: "k", ctrlKey: true })

    await waitFor(() => {
      expect(screen.getByTestId("command-palette-shell")).toHaveTextContent("open")
    })
  })

  it("hides the terminal toggle on non-terminal routes", async () => {
    pathnameState.value = "/dashboard"

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "accessibility.openTerminal" })).not.toBeInTheDocument()
    })
  })
})
