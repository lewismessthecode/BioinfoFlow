import { renderHook, waitFor, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useSidebarData } from "@/hooks/use-sidebar-data"
import { apiRequest } from "@/lib/api"
import type { AgentSessionSummary } from "@/lib/agent/client"
import {
  publishAgentSessionSummary,
  publishConversationSummary,
} from "@/lib/agent/session-preferences"
import type { Project } from "@/lib/types"
import { createAppWrapper } from "@/tests/app-test-utils"

const { pushMock, replaceMock, pathnameMock, toastErrorMock, toastSuccessMock, celebrateMilestoneMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  pathnameMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  celebrateMilestoneMock: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  usePathname: () => pathnameMock(),
}))

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
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

describe("useSidebarData", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const tSidebar = (key: string, values?: Record<string, string>) =>
    values?.name ? `${key}:${values.name}` : key

  const session = (
    overrides: Partial<AgentSessionSummary> & Pick<AgentSessionSummary, "id" | "project_id">,
  ): AgentSessionSummary => ({
    title: null,
    permission_mode: "ask_changes",
    workspace_access: "read_write",
    status: "active",
    created_at: "2026-06-04T00:00:00Z",
    updated_at: "2026-06-04T00:00:00Z",
    ...overrides,
  })

  beforeEach(() => {
    apiRequestMock.mockReset()
    pushMock.mockReset()
    replaceMock.mockReset()
    pathnameMock.mockReset()
    pathnameMock.mockReturnValue("/agent")
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    celebrateMilestoneMock.mockReset()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it("sorts projects alphabetically without prefix-based special cases", async () => {
    const projects: Project[] = [
      { id: "project-default", name: "Recent", project_root: "asset://project", storage_mode: "managed", is_default: true },
      { id: "project-z", name: "Zeta", project_root: "asset://project", storage_mode: "managed" },
      { id: "project-demo", name: "Archive/Alpha", project_root: "asset://project", storage_mode: "managed" },
      { id: "project-a", name: "Alpha", project_root: "asset://project", storage_mode: "managed" },
    ]

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") {
        return { data: projects, meta: undefined }
      }
      if (path === "/projects/default") {
        return { data: projects[0], meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() =>
      expect(result.current.sidebar.projects.map((project) => project.id)).toEqual([
        "project-a",
        "project-demo",
        "project-z",
      ])
    )

    await waitFor(() => {
      expect(result.current.project.selectedProjectId).toBe("project-a")
      expect(result.current.project.conversationProjectId).toBe("project-a")
      expect(result.current.project.activeProjectName).toBe("Alpha")
    })
  })

  it("loads the public session list once and groups sessions by project", async () => {
    const projects: Project[] = [
      { id: "project-default", name: "Recent", project_root: "asset://project", storage_mode: "managed", is_default: true },
      { id: "project-a", name: "Alpha", project_root: "asset://project", storage_mode: "managed" },
      { id: "project-b", name: "Bravo", project_root: "asset://project", storage_mode: "managed" },
    ]
    const conversations: AgentSessionSummary[] = [
      session({ id: "session-b", project_id: "project-b", title: "Bravo run" }),
      session({ id: "session-a", project_id: "project-a", title: "Alpha run" }),
      session({ id: "session-recent", project_id: "project-default", title: "Recent run" }),
    ]

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") return { data: projects, meta: undefined }
      if (path === "/projects/default") return { data: projects[0], meta: undefined }
      if (path === "/agent/sessions") return { data: conversations, meta: undefined }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({ selectedProjectId: "project-a" })
    const { result } = renderHook(() => useSidebarData(tSidebar), { wrapper: Wrapper })

    await waitFor(() => {
      expect(result.current.projectConversations.get("project-a")?.map((item) => item.id)).toEqual([
        "session-a",
      ])
      expect(result.current.projectConversations.get("project-b")?.map((item) => item.id)).toEqual([
        "session-b",
      ])
      expect(result.current.inboxConversations.map((item) => item.id)).toEqual([
        "session-recent",
      ])
    })

    expect(
      apiRequestMock.mock.calls.filter(([path]) => path === "/agent/sessions"),
    ).toHaveLength(1)
  })

  it("keeps the active project on a draft when no conversation is explicitly selected", async () => {
    const project: Project = {
      id: "project-1",
      name: "Alpha",
      project_root: "asset://project",
      storage_mode: "managed",
    }
    const conversations = [
      session({ id: "session-1", project_id: "project-1", title: "Existing run" }),
    ]

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") {
        return { data: [project], meta: undefined }
      }
      if (path === "/projects/default") {
        throw new Error("no default")
      }
      if (path === "/agent/sessions") {
        return { data: conversations, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "",
    })
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper },
    )

    await waitFor(() =>
      expect(result.current.sidebar.projectConversations.get(project.id)).toEqual(
        conversations,
      ),
    )

    expect(result.current.project.activeConversationId).toBe("")
  })

  it("creates a project without requiring workspace (auto-generated by dialog)", async () => {
    const apiProjects: Project[] = []
    const createdProject: Project = {
      id: "project-new",
      name: "My Analysis",
      project_root: "asset://project",
      storage_mode: "managed",
    }

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects" && options?.method === "POST") {
        return { data: createdProject, meta: undefined }
      }
      if (path === "/projects") {
        return { data: apiProjects, meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() => expect(result.current.sidebar.isLoading).toBe(false))

    // Should NOT throw when workspace is empty
    await act(async () => {
      await result.current.sidebar.handleCreateProject({
        name: "My Analysis",
        description: "",
        storageOverridePath: "",
      })
    })

    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(toastSuccessMock).toHaveBeenCalled()
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-project")
  })

  it("creates a remote project with remote connection fields", async () => {
    const createdProject: Project = {
      id: "project-remote",
      name: "Phoenix sample",
      project_root: "ssh://11111111-1111-1111-1111-111111111111/inspurfsms102/B2C_RD1/sample",
      storage_mode: "remote",
      remote_connection_id: "11111111-1111-1111-1111-111111111111",
      remote_root_path: "/inspurfsms102/B2C_RD1/sample",
    }

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects" && options?.method === "POST") {
        return { data: createdProject, meta: undefined }
      }
      if (path === "/projects") {
        return { data: [], meta: undefined }
      }
      if (path === "/projects/default") {
        throw new Error("no default")
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.sidebar.isLoading).toBe(false))

    await act(async () => {
      await result.current.sidebar.handleCreateProject({
        name: "Phoenix sample",
        description: "Remote shared storage",
        projectType: "remote",
        remoteConnectionId: "11111111-1111-1111-1111-111111111111",
        remoteRootPath: "/inspurfsms102/B2C_RD1/sample",
      })
    })

    const postCall = apiRequestMock.mock.calls.find(
      ([path, opts]) => path === "/projects" && opts?.method === "POST",
    )
    expect(JSON.parse(postCall![1]!.body as string)).toEqual({
      name: "Phoenix sample",
      description: "Remote shared storage",
      remote_connection_id: "11111111-1111-1111-1111-111111111111",
      remote_root_path: "/inspurfsms102/B2C_RD1/sample",
    })
    expect(result.current.project.activeProjectId).toBe("project-remote")
  })

  it("quick-creates a project with only name and description (no workspace)", async () => {
    const createdProject: Project = {
      id: "project-quick",
      name: "WGS Analysis",
      project_root: "asset://project",
      storage_mode: "managed",
    }

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects" && options?.method === "POST") {
        return { data: createdProject, meta: undefined }
      }
      if (path === "/projects") {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() => expect(result.current.sidebar.isLoading).toBe(false))

    await act(async () => {
      await result.current.sidebar.handleQuickCreateProject({
        name: "WGS Analysis",
        description: "Whole genome sequencing variant calling",
      })
    })

    // Should POST with name and description only (no workspace_path)
    const postCall = apiRequestMock.mock.calls.find(
      ([path, opts]) => path === "/projects" && opts?.method === "POST"
    )
    expect(postCall).toBeDefined()
    const body = JSON.parse(postCall![1]!.body as string)
    expect(body).toEqual({
      name: "WGS Analysis",
      description: "Whole genome sequencing variant calling",
    })
    expect(body).not.toHaveProperty("workspace_path")

    expect(toastSuccessMock).toHaveBeenCalled()
    expect(result.current.project.activeProjectId).toBe("project-quick")
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-project")
  })

  it("starts an inbox draft when no real project is selected", async () => {
    const defaultProject: Project = {
      id: "project-default",
      name: "Recent",
      project_root: "asset://project",
      storage_mode: "managed",
      is_default: true,
    }

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects") {
        return { data: [defaultProject], meta: undefined }
      }
      if (path === "/projects/default") {
        return { data: defaultProject, meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      if (options?.method === "POST") {
        throw new Error(`Unexpected POST: ${path}`)
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() => expect(result.current.sidebar.defaultProject?.id).toBe("project-default"))

    await act(async () => {
      await result.current.sidebar.handleCreateConversation()
    })

    const postCall = apiRequestMock.mock.calls.find(
      ([path, opts]) => path === "/agent/sessions" && opts?.method === "POST"
    )
    expect(postCall).toBeUndefined()
    expect(result.current.project.selectedProjectId).toBe("")
    expect(result.current.project.conversationProjectId).toBe("project-default")
    expect(result.current.project.activeConversationId).toBe("")
    expect(pushMock).toHaveBeenCalledWith("/agent")
  })

  it("keeps repeated new conversation clicks on the same empty draft", async () => {
    const project: Project = {
      id: "project-1",
      name: "Alpha",
      project_root: "asset://project",
      storage_mode: "managed",
    }

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects") {
        return { data: [project], meta: undefined }
      }
      if (path === "/projects/default") {
        throw new Error("no default")
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      if (options?.method === "POST") {
        throw new Error(`Unexpected POST: ${path}`)
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({ selectedProjectId: "project-1" })
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() => expect(result.current.sidebar.projects).toHaveLength(1))

    await act(async () => {
      await result.current.sidebar.handleCreateConversation(project.id)
    })
    await act(async () => {
      await result.current.sidebar.handleCreateConversation(project.id)
    })

    expect(apiRequestMock.mock.calls.some(([path]) => String(path).includes("/agent/conversations"))).toBe(false)
    expect(
      apiRequestMock.mock.calls.some(
        ([path, options]) => path === "/agent/sessions" && options?.method === "POST",
      ),
    ).toBe(false)
    expect(result.current.sidebar.projectConversations.get(project.id) ?? []).toEqual([])
    expect(result.current.project.conversationProjectId).toBe("project-1")
    expect(result.current.project.activeConversationId).toBe("")
  })

  it("updates session titles from public summary events", async () => {
    const project: Project = {
      id: "project-1",
      name: "Alpha",
      project_root: "asset://project",
      storage_mode: "managed",
    }
    const conversations: AgentSessionSummary[] = [
      session({ id: "session-1", project_id: project.id, title: null }),
    ]

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects") {
        return { data: [project], meta: undefined }
      }
      if (path === "/projects/default") {
        throw new Error("no default")
      }
      if (path === "/agent/sessions") {
        return { data: conversations, meta: undefined }
      }
      if (options?.method === "POST") {
        throw new Error(`Unexpected POST: ${path}`)
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({ selectedProjectId: "project-1" })
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() => expect(result.current.sidebar.projects).toHaveLength(1))
    act(() => {
      publishConversationSummary({
        id: "session-1",
        projectId: project.id,
        workspaceId: "workspace-1",
        title: "Started analysis",
        status: "active",
      })
    })

    expect(
      apiRequestMock.mock.calls.some(
        ([path]) => String(path).includes("/agent/conversations"),
      ),
    ).toBe(false)
    expect(result.current.sidebar.projectConversations.get(project.id)).toEqual([
      {
        ...conversations[0],
        title: "Started analysis",
      },
    ])
  })

  it("adds newly created default-project sessions to the workspace inbox from update events", async () => {
    const defaultProject: Project = {
      id: "project-default",
      name: "Recent",
      project_root: "asset://project",
      storage_mode: "managed",
      is_default: true,
    }

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") {
        return { data: [defaultProject], meta: undefined }
      }
      if (path === "/projects/default") {
        return { data: defaultProject, meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper },
    )

    await waitFor(() =>
      expect(result.current.sidebar.defaultProject?.id).toBe(defaultProject.id),
    )
    await waitFor(() =>
      expect(result.current.sidebar.inboxConversations).toEqual([]),
    )

    act(() => {
      publishAgentSessionSummary(
        session({
          id: "session-new",
          project_id: defaultProject.id,
          title: "Workspace analysis",
          updated_at: "2026-06-04T00:00:05Z",
        }),
      )
    })

    expect(result.current.sidebar.inboxConversations).toEqual([
      expect.objectContaining({
        id: "session-new",
        project_id: defaultProject.id,
        title: "Workspace analysis",
      }),
    ])
  })

  it("deletes an existing Agent session", async () => {
    const project: Project = {
      id: "project-1",
      name: "Alpha",
      project_root: "asset://project",
      storage_mode: "managed",
    }
    const emptyConversation = session({
      id: "session-empty",
      project_id: project.id,
      title: null,
    })
    pathnameMock.mockReturnValue("/agent/session-empty")

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/projects") {
        return { data: [project], meta: undefined }
      }
      if (path === "/projects/default") {
        throw new Error("no default")
      }
      if (path === "/agent/sessions/session-empty" && options?.method === "DELETE") {
        return { data: null, meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [emptyConversation], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "session-empty",
    })
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() =>
      expect(result.current.sidebar.projectConversations.get(project.id)).toEqual([
        emptyConversation,
      ])
    )

    await act(async () => {
      await result.current.sidebar.handleDeleteConversation("session-empty", project.id)
    })

    expect(apiRequestMock).toHaveBeenCalledWith(
      "/agent/sessions/session-empty",
      { method: "DELETE" },
    )
    expect(result.current.sidebar.projectConversations.get(project.id) ?? []).toEqual([])
    expect(replaceMock).toHaveBeenCalledWith("/agent")
  })

  it("selects a conversation and navigates to the session route", async () => {
    const apiProjects: Project[] = [{ id: "project-1", name: "Alpha", project_root: "asset://project" }]

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") {
        return { data: apiProjects, meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper()
    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )
    const conversation = session({
      id: "session-9",
      project_id: "project-1",
      title: "Genome QC",
    })

    await waitFor(() => expect(result.current.sidebar.projects).toHaveLength(1))

    act(() => {
      result.current.sidebar.handleSelectConversation(conversation, "project-1")
    })

    expect(result.current.project.activeProjectId).toBe("project-1")
    expect(result.current.project.activeConversationId).toBe("session-9")
    expect(pushMock).toHaveBeenCalledWith("/agent/session-9")
  })

  it("updates sidebar conversation titles when the active chat emits a title refresh", async () => {
    const apiProjects: Project[] = [{ id: "project-1", name: "Alpha", project_root: "asset://project" }]
    const conversations: AgentSessionSummary[] = [
      session({ id: "session-1", project_id: "project-1", title: null }),
    ]

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") {
        return { data: apiProjects, meta: undefined }
      }
      if (path === "/projects/default") {
        throw new Error("no default")
      }
      if (path === "/agent/sessions") {
        return { data: conversations, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      selectedProjectId: "project-1",
      conversationProjectId: "project-1",
      activeConversationId: "session-1",
    })

    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() =>
      expect(result.current.project.activeConversationTitle).toBe("")
    )

    act(() => {
      publishConversationSummary({
        id: "session-1",
        projectId: "project-1",
        workspaceId: "workspace-1",
        title: "RNA-seq QC Plan",
        status: "active",
      })
    })

    await waitFor(() =>
      expect(result.current.project.activeConversationTitle).toBe("RNA-seq QC Plan")
    )
  })
})
