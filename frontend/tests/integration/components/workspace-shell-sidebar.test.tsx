import * as React from "react"
import { fireEvent, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "@/components/bioinfoflow/sidebar"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { WorkspaceShellProvider } from "@/components/bioinfoflow/workspace-shell-context"
import { apiRequest } from "@/lib/api"
import { createAppWrapper } from "@/tests/app-test-utils"
import { renderWithProviders } from "@/tests/test-utils"

const {
  routerPushMock,
  toastErrorMock,
  toastSuccessMock,
} = vi.hoisted(() => ({
  routerPushMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}))

const stableRouter = {
  push: routerPushMock,
}

const translationMap = new Map<string, (key: string, values?: Record<string, unknown>) => string>()

function getTranslation(namespace: string) {
  if (!translationMap.has(namespace)) {
    translationMap.set(namespace, (key: string, values?: Record<string, unknown>) => {
      const suffix = values
        ? Object.values(values)
            .filter((value) => value !== undefined && value !== null)
            .join(":")
        : ""
      return suffix ? `${namespace}.${key}:${suffix}` : `${namespace}.${key}`
    })
  }
  return translationMap.get(namespace)!
}

vi.mock("next/navigation", () => ({
  useRouter: () => stableRouter,
  usePathname: () => "/agent",
}))

vi.mock("next-intl", () => ({
  useLocale: () => "zh-CN",
  useTranslations: (namespace: string) => getTranslation(namespace),
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

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}))

vi.mock("@/components/bioinfoflow/user-menu", () => ({
  UserMenu: () => <div data-testid="user-menu" />,
}))

vi.mock("@/components/bioinfoflow/logo", () => ({
  Logo: () => <div data-testid="logo" />,
}))

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

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

vi.mock("@/components/bioinfoflow/create-project-dialog", () => ({
  CreateProjectDialog: ({
    externalOpen,
    onExternalOpenChange,
    onCreateProject,
  }: {
    externalOpen?: boolean
    onExternalOpenChange?: (open: boolean) => void
    onCreateProject: (data: {
      name: string
      description: string
      storageOverridePath?: string
      projectType?: "local" | "remote"
      remoteConnectionId?: string
      remoteRootPath?: string
    }) => Promise<void>
  }) => {
    const [name, setName] = React.useState("")
    const [description, setDescription] = React.useState("")

    if (!externalOpen) return null

    return (
      <div data-testid="create-project-dialog">
        <input
          aria-label="sidebar.projectName"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <input
          aria-label="sidebar.projectDescription"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <button
          onClick={async () => {
            await onCreateProject({ name, description })
          }}
        >
          sidebar.createProject
        </button>
        <button onClick={() => onExternalOpenChange?.(false)}>common.cancel</button>
      </div>
    )
  },
}))

vi.mock("@/components/bioinfoflow/sidebar/delete-confirm-dialog", () => ({
  DeleteConfirmDialog: ({
    deleteConfirm,
    onCancel,
    onConfirm,
  }: {
    deleteConfirm: { name: string } | null
    onCancel: () => void
    onConfirm: () => void
  }) =>
    deleteConfirm ? (
      <div data-testid="delete-confirm-dialog">
        <div>{deleteConfirm.name}</div>
        <button onClick={onConfirm}>common.delete</button>
        <button onClick={onCancel}>common.cancel</button>
      </div>
    ) : null,
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

type ProjectRecord = {
  id: string
  name: string
  project_root: string
  storage_mode: string
  is_default?: boolean
}

type ConversationRecord = {
  id: string
  project_id: string
  title: string
  pinned?: boolean
}

function ProjectContextProbe() {
  const context = useProjectContext()

  return (
    <dl>
      <div data-testid="selected-project-id">{context.selectedProjectId}</div>
      <div data-testid="conversation-project-id">{context.conversationProjectId}</div>
      <div data-testid="active-conversation-id">{context.activeConversationId}</div>
      <div data-testid="active-project-name">{context.activeProjectName}</div>
      <div data-testid="active-conversation-title">{context.activeConversationTitle}</div>
    </dl>
  )
}

describe("WorkspaceShell sidebar integration", () => {
  const apiRequestMock = vi.mocked(apiRequest)

  let projectsState: ProjectRecord[]
  let defaultProject: ProjectRecord
  let conversationsState: Map<string, ConversationRecord[]>
  let createdProjectCounter: number

  const renderSidebar = () => {
    const ProjectWrapper = createAppWrapper()
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <ProjectWrapper>
        <WorkspaceShellProvider>{children}</WorkspaceShellProvider>
      </ProjectWrapper>
    )

    return renderWithProviders(
      <>
        <Sidebar collapsed={false} />
        <ProjectContextProbe />
      </>,
      { wrapper },
    )
  }

  beforeEach(() => {
    routerPushMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    window.localStorage.clear()

    defaultProject = {
      id: "project-default",
      name: "Recent",
      project_root: "asset://default",
      storage_mode: "managed",
      is_default: true,
    }

    projectsState = [
      {
        id: "project-alpha",
        name: "Alpha",
        project_root: "asset://alpha",
        storage_mode: "managed",
      },
      {
        id: "project-beta",
        name: "Beta",
        project_root: "asset://beta",
        storage_mode: "managed",
      },
    ]

    conversationsState = new Map<string, ConversationRecord[]>([
      [
        defaultProject.id,
        [
          {
            id: "conv-inbox-1",
            project_id: defaultProject.id,
            title: "Inbox thread",
          },
        ],
      ],
      [
        "project-alpha",
        [
          {
            id: "conv-alpha-1",
            project_id: "project-alpha",
            title: "Alpha thread",
          },
        ],
      ],
      [
        "project-beta",
        [
          {
            id: "conv-beta-1",
            project_id: "project-beta",
            title: "Beta thread",
          },
        ],
      ],
    ])

    createdProjectCounter = 0

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects" && options?.method === "POST") {
        createdProjectCounter += 1
        const body = JSON.parse(String(options.body)) as { name: string; description?: string | null }
        const createdProject = {
          id: `project-created-${createdProjectCounter}`,
          name: body.name,
          description: body.description ?? null,
          project_root: `asset://${body.name.toLowerCase()}`,
          storage_mode: "managed",
        }
        projectsState = [createdProject, ...projectsState]
        conversationsState.set(createdProject.id, [])
        return { data: createdProject, meta: undefined }
      }

      if (path === "/projects" && options?.method === "DELETE") {
        throw new Error("Unexpected bulk delete")
      }

      if (typeof path === "string" && path.startsWith("/projects/") && options?.method === "DELETE") {
        const projectId = path.replace("/projects/", "")
        projectsState = projectsState.filter((project) => project.id !== projectId)
        conversationsState.delete(projectId)
        return { data: null, meta: undefined }
      }

      if (path === "/projects") {
        return { data: [...projectsState], meta: undefined }
      }

      if (path === "/projects/default") {
        return { data: defaultProject, meta: undefined }
      }

      if (path === "/agent/sessions") {
        const projectId = String(options?.params?.project_id ?? "")
        return {
          data: [...(conversationsState.get(projectId) ?? [])],
          meta: undefined,
        }
      }

      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("creates a project, switches context, and clears context when the selected project is deleted", async () => {
    renderSidebar()

    expect(await screen.findByRole("button", { name: "Alpha" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Beta" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "sidebar.newProject" }))
    expect(await screen.findByTestId("create-project-dialog")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("sidebar.projectName"), {
      target: { value: "Gamma" },
    })
    fireEvent.change(screen.getByLabelText("sidebar.projectDescription"), {
      target: { value: "New workspace" },
    })
    fireEvent.click(screen.getByRole("button", { name: "sidebar.createProject" }))

    expect(await screen.findByRole("button", { name: "Gamma" })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId("selected-project-id")).toHaveTextContent("project-created-1"))
    await waitFor(() => expect(screen.getByTestId("active-project-name")).toHaveTextContent("Gamma"))

    fireEvent.click(screen.getByRole("button", { name: "Beta" }))
    await waitFor(() => expect(screen.getByTestId("selected-project-id")).toHaveTextContent("project-beta"))
    await waitFor(() => expect(screen.getByTestId("active-project-name")).toHaveTextContent("Beta"))

    const betaHeader = screen.getByRole("button", { name: "Beta" }).parentElement
    expect(betaHeader).not.toBeNull()
    fireEvent.click(within(betaHeader as HTMLElement).getByRole("button", { name: "common.actions" }))
    fireEvent.click(within(betaHeader as HTMLElement).getByRole("button", { name: "common.delete" }))
    const deleteDialog = await screen.findByTestId("delete-confirm-dialog")
    fireEvent.click(within(deleteDialog).getByRole("button", { name: "common.delete" }))

    await waitFor(() => expect(screen.queryByRole("button", { name: "Beta" })).not.toBeInTheDocument())
    await waitFor(() =>
      expect(screen.getByTestId("selected-project-id")).toHaveTextContent("project-created-1"),
    )
    expect(screen.getByTestId("conversation-project-id")).toHaveTextContent("project-created-1")
    expect(screen.getByTestId("active-conversation-id")).toHaveTextContent("")
    await waitFor(() =>
      expect(screen.getByTestId("active-project-name")).toHaveTextContent("Gamma"),
    )
  })

  it("selects a conversation from the sidebar and syncs project context before navigating", async () => {
    renderSidebar()

    const alphaHeader = (await screen.findByRole("button", { name: "Alpha" })).parentElement
    expect(alphaHeader).not.toBeNull()

    fireEvent.click(within(alphaHeader as HTMLElement).getByRole("button", { name: "Alpha" }))

    const conversationButton = await screen.findByRole("button", { name: "Alpha thread" })
    fireEvent.click(conversationButton)

    await waitFor(() => expect(screen.getByTestId("selected-project-id")).toHaveTextContent("project-alpha"))
    expect(screen.getByTestId("conversation-project-id")).toHaveTextContent("project-alpha")
    expect(screen.getByTestId("active-conversation-id")).toHaveTextContent("conv-alpha-1")
    expect(screen.getByTestId("active-project-name")).toHaveTextContent("Alpha")
    expect(screen.getByTestId("active-conversation-title")).toHaveTextContent("Alpha thread")
    expect(routerPushMock).toHaveBeenCalledWith("/agent/conv-alpha-1")
  })

  it("restores the last used regular project into workspace context on /agent", async () => {
    window.localStorage.setItem("bioinfoflow:last-used-project", "project-beta")

    renderSidebar()

    await waitFor(() =>
      expect(screen.getByTestId("selected-project-id")).toHaveTextContent("project-beta"),
    )
    expect(screen.getByTestId("conversation-project-id")).toHaveTextContent("project-beta")
    expect(screen.getByTestId("active-conversation-id")).toHaveTextContent("")
    await waitFor(() =>
      expect(screen.getByTestId("active-project-name")).toHaveTextContent("Beta"),
    )
  })

  it("renders the airy Bioinfoflow sidebar brand without the old tile shadow", async () => {
    renderSidebar()

    const logo = await screen.findByTestId("logo")

    expect(screen.getByText("Bioinfoflow")).toBeInTheDocument()
    expect(logo.parentElement?.className).not.toContain("shadow-sm")
  })
})
