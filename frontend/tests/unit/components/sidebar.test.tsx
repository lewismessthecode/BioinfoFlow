import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi, beforeEach } from "vitest"

const useWorkspaceShellMock = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

vi.mock("next/link", () => ({
  default: ({ children, href, className }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}))

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, Record<string, string>> = {
      sidebar: {
        newAnalysis: "New Analysis",
        workspace: "Workspace",
      },
      common: {
        actions: "Actions",
      },
      nav: {
        settings: "Settings",
      },
      welcome: {
        title: "Start your first analysis",
      },
    }

    return copy[namespace]?.[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/project-context", () => ({
  useProjectContext: () => ({
    activeProjectId: "",
    activeConversationId: "",
  }),
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useWorkspaceShell: (...args: unknown[]) => useWorkspaceShellMock(...args),
}))

vi.mock("@/components/bioinfoflow/user-menu", () => ({
  UserMenu: () => <div data-testid="user-menu" />,
}))

vi.mock("@/components/bioinfoflow/create-project-dialog", () => ({
  CreateProjectDialog: () => <div data-testid="create-project-dialog" />,
}))

vi.mock("@/components/bioinfoflow/sidebar/sidebar-nav", () => ({
  SidebarNav: () => <div data-testid="sidebar-nav" />,
}))

vi.mock("@/components/bioinfoflow/sidebar/project-list", () => ({
  ProjectList: () => <div data-testid="project-list" />,
}))

vi.mock("@/components/bioinfoflow/sidebar/conversation-item", () => ({
  ConversationItem: () => <div data-testid="conversation-item" />,
}))

vi.mock("@/components/bioinfoflow/sidebar/delete-confirm-dialog", () => ({
  DeleteConfirmDialog: () => null,
}))

import { Sidebar } from "@/components/bioinfoflow/sidebar/sidebar"

describe("Sidebar", () => {
  beforeEach(() => {
    useWorkspaceShellMock.mockReset()
    useWorkspaceShellMock.mockReturnValue({
      projects: [],
      defaultProject: null,
      isLoading: false,
      expandedProjects: new Set(),
      projectConversations: new Map(),
      loadingProjects: new Set(),
      toggleProjectExpanded: vi.fn(),
      handleSelectProject: vi.fn(),
      handleCreateProject: vi.fn(),
      handleQuickCreateProject: vi.fn(),
      handleRenameProject: vi.fn(),
      handleDuplicateProject: vi.fn(),
      handleDeleteProject: vi.fn(),
      handleSelectConversation: vi.fn(),
      handleCreateConversation: vi.fn(),
      handleRenameConversation: vi.fn(),
      handleTogglePin: vi.fn(),
      handleDeleteConversation: vi.fn(),
      createProjectDialogOpen: false,
      openCreateProjectDialog: vi.fn(),
      setCreateProjectDialogOpen: vi.fn(),
      hasProjects: false,
    })
  })

  it("uses New Analysis as the primary CTA", () => {
    render(<Sidebar collapsed={false} />)

    expect(screen.getByRole("button", { name: "New Analysis" })).toBeInTheDocument()
  })

  it("renders the New Analysis CTA without elevated styling", () => {
    render(<Sidebar collapsed={false} />)

    const button = screen.getByRole("button", { name: "New Analysis" })
    expect(button.className).not.toContain("shadow-sm")
  })

  it("moves settings out of the standalone footer nav", () => {
    render(<Sidebar collapsed={false} />)

    expect(screen.queryByRole("link", { name: "Settings" })).not.toBeInTheDocument()
  })

  it("keeps the sidebar sparse when there are no projects", () => {
    render(<Sidebar collapsed={false} />)

    expect(screen.queryByText("Start your first analysis")).not.toBeInTheDocument()
  })
})
