import * as React from "react"
import { screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import AppLayout from "@/app/(app)/app-layout"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useTerminalDock } from "@/components/bioinfoflow/terminal/terminal-dock-context"
import { renderAppPage } from "@/tests/app-test-utils"

const pathnameState = {
  value: "/agent",
}

vi.mock("next/navigation", () => ({
  usePathname: () => pathnameState.value,
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
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  WorkspaceShellProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock("@/components/bioinfoflow/sidebar/sidebar-drawer", () => ({
  SidebarDrawer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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

function ProjectSeeder({ projectId }: { projectId: string }) {
  const { setActiveProjectId } = useProjectContext()

  React.useEffect(() => {
    setActiveProjectId(projectId)
  }, [projectId, setActiveProjectId])

  return <div>page</div>
}

describe("AppLayout terminal integration", () => {
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

    toggle.click()

    await waitFor(() => {
      expect(screen.getByTestId("terminal-dock")).toHaveTextContent("open")
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
