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
let terminalDockProps: Record<string, unknown> | null = null
let workspaceSessionScope:
  | Map<string, Array<{ id: string; project_id: string | null }>>
  | null
  | undefined = null

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

      terminalDockProps = props
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
  useOptionalWorkspaceShell: () =>
    workspaceSessionScope === null
      ? null
      : { projectConversations: workspaceSessionScope },
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

function TerminalIdentityProbe() {
  const { projectId, enabled } = useTerminalDock()
  return (
    <span data-testid="terminal-identity">
      {enabled ? projectId ?? "none" : "disabled"}
    </span>
  )
}

describe("AppLayout terminal integration", () => {
  beforeEach(() => {
    workspaceNavbarActions = null
    terminalDockProps = null
    workspaceSessionScope = null
    searchParamsState.value = new URLSearchParams()
    localStorage.clear()
  })

  it("does not expose a stale terminal during direct route resolution", async () => {
    pathnameState.value = "/agent/session-b"
    workspaceSessionScope = new Map()

    const view = renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-a" />
        <TerminalIdentityProbe />
      </AppLayout>,
    )

    expect(screen.getByTestId("terminal-identity")).toHaveTextContent("disabled")
    expect(screen.queryByRole("button", { name: "accessibility.openTerminal" })).not.toBeInTheDocument()

    workspaceSessionScope = new Map([
      ["project-b", [{ id: "session-b", project_id: "project-b" }]],
    ])
    view.rerender(
      <AppLayout>
        <TerminalIdentityProbe />
      </AppLayout>,
    )

    await waitFor(() =>
      expect(screen.getByTestId("terminal-identity")).toHaveTextContent("project-b"),
    )
    expect(screen.getByRole("button", { name: "accessibility.openTerminal" })).toBeInTheDocument()
  })

  it("handles an unresolved workspace session collection safely", () => {
    pathnameState.value = "/agent/session-loading"
    workspaceSessionScope = undefined

    expect(() =>
      renderAppPage(
        <AppLayout>
          <ProjectSeeder projectId="project-a" />
          <TerminalIdentityProbe />
        </AppLayout>,
      ),
    ).not.toThrow()
    expect(screen.getByTestId("terminal-identity")).toHaveTextContent("disabled")
  })

  it("shows the terminal toggle on terminal-enabled routes when a project is active", async () => {
    pathnameState.value = "/agent"

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>
    )

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "accessibility.openTerminal" }))
        .toHaveAttribute("data-navbar-action", "terminal")
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

  it("does not let a user-controlled query enable the screenshot fixture", async () => {
    pathnameState.value = "/agent"
    searchParamsState.value = new URLSearchParams("e2eTerminalFixture=1")

    renderAppPage(
      <AppLayout>
        <ProjectSeeder projectId="project-1" />
      </AppLayout>,
    )

    await screen.findByRole("button", { name: "accessibility.openTerminal" })
    await waitFor(() => {
      expect(terminalDockProps).toEqual({ screenshotFixture: false })
    })
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
      <button type="button" className="h-8 w-8" aria-label="Open workspace panel" />
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
      "Open workspace panel",
    ])
    expect(buttons[0]).toHaveClass("h-8", "w-8")
    expect(buttons[1]).toHaveClass("h-8", "w-8")
  })

  it("does not mount the command palette until the shortcut is used", async () => {
    pathnameState.value = "/dashboard"

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
