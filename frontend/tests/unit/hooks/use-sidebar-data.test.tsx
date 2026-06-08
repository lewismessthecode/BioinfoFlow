import { renderHook, waitFor, act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useSidebarData } from "@/hooks/use-sidebar-data"
import { apiRequest } from "@/lib/api"
import { emitAgentSessionUpdated } from "@/lib/agent-core/session-storage"
import type { AgentCoreSession } from "@/lib/agent-core"
import type { Project } from "@/lib/types"
import { createAppWrapper } from "@/tests/app-test-utils"

const { pushMock, toastErrorMock, toastSuccessMock, emitReadinessRefreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  emitReadinessRefreshMock: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
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

vi.mock("@/lib/readiness-events", () => ({
  emitReadinessRefresh: (...args: unknown[]) => emitReadinessRefreshMock(...args),
}))

describe("useSidebarData", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const tSidebar = (key: string, values?: Record<string, string>) =>
    values?.name ? `${key}:${values.name}` : key

  const session = (
    overrides: Partial<AgentCoreSession> & Pick<AgentCoreSession, "id" | "project_id">,
  ): AgentCoreSession => ({
    workspace_id: "workspace-1",
    user_id: "dev",
    title: null,
    role_profile: "bioinformatician",
    permission_mode: "guarded_auto",
    automation_mode: "assisted",
    default_model_profile_id: null,
    status: "active",
    metadata: null,
    created_at: "2026-06-04T00:00:00Z",
    updated_at: "2026-06-04T00:00:00Z",
    ...overrides,
  })

  beforeEach(() => {
    apiRequestMock.mockReset()
    pushMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    emitReadinessRefreshMock.mockReset()
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

    expect(result.current.project.selectedProjectId).toBe("project-a")
    expect(result.current.project.conversationProjectId).toBe("project-a")
    expect(result.current.project.activeProjectName).toBe("Alpha")
  })

  it("restores the last used regular project into the assistant workspace", async () => {
    const projects: Project[] = [
      { id: "project-default", name: "Recent", project_root: "asset://project", storage_mode: "managed", is_default: true },
      { id: "project-2", name: "Beta", project_root: "asset://project", storage_mode: "managed" },
      { id: "project-1", name: "Alpha", project_root: "asset://project", storage_mode: "managed" },
    ]

    window.localStorage.setItem("bioinfoflow:last-used-project", "project-2")

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

    await waitFor(() => expect(result.current.project.selectedProjectId).toBe("project-2"))
    expect(result.current.project.conversationProjectId).toBe("project-2")
    expect(window.localStorage.getItem("bioinfoflow:last-used-project")).toBe("project-2")
  })

  it("falls back to the first regular project when the stored project no longer exists", async () => {
    const projects: Project[] = [
      { id: "project-default", name: "Recent", project_root: "asset://project", storage_mode: "managed", is_default: true },
      { id: "project-b", name: "Beta", project_root: "asset://project", storage_mode: "managed" },
      { id: "project-a", name: "Alpha", project_root: "asset://project", storage_mode: "managed" },
    ]

    window.localStorage.setItem("bioinfoflow:last-used-project", "project-missing")

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

    await waitFor(() => expect(result.current.project.selectedProjectId).toBe("project-a"))
    expect(result.current.project.conversationProjectId).toBe("project-a")
    expect(window.localStorage.getItem("bioinfoflow:last-used-project")).toBe("project-a")
  })

  it("restores the stored conversation for the active project when available", async () => {
    const projects: Project[] = [
      { id: "project-1", name: "Alpha", project_root: "asset://project", storage_mode: "managed" },
    ]
    const conversations: AgentCoreSession[] = [
      session({ id: "session-1", project_id: "project-1", title: "First" }),
      session({ id: "session-2", project_id: "project-1", title: "Second" }),
    ]

    window.localStorage.setItem("bioinfoflow:agent-core-session:project-1", "session-2")

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/projects") {
        return { data: projects, meta: undefined }
      }
      if (path === "/agent/sessions") {
        return { data: conversations, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
    })

    const { result } = renderHook(
      () => ({ sidebar: useSidebarData(tSidebar), project: useProjectContext() }),
      { wrapper: Wrapper }
    )

    await waitFor(() =>
      expect(result.current.project.activeConversationId).toBe("session-2")
    )
    expect(result.current.project.activeConversationTitle).toBe("Second")
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
    expect(window.localStorage.getItem("bioinfoflow:agent-core-session:project-1")).toBeNull()
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
    expect(emitReadinessRefreshMock).toHaveBeenCalledWith("project-created")
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
    expect(emitReadinessRefreshMock).toHaveBeenCalledWith("project-created")
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
    expect(window.localStorage.getItem("bioinfoflow:agent-core-session:project-default")).toBeNull()
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
    expect(result.current.sidebar.projectConversations.get(project.id)).toEqual([])
    expect(result.current.project.conversationProjectId).toBe("project-1")
    expect(result.current.project.activeConversationId).toBe("")
    expect(window.localStorage.getItem("bioinfoflow:agent-core-session:project-1")).toBeNull()
  })

  it("updates session titles from AgentCore session update events", async () => {
    const project: Project = {
      id: "project-1",
      name: "Alpha",
      project_root: "asset://project",
      storage_mode: "managed",
    }
    const conversations: AgentCoreSession[] = [
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
      emitAgentSessionUpdated({
        id: "session-1",
        project_id: project.id,
        title: "Started analysis",
        created_at: "2026-06-04T00:00:00Z",
        updated_at: "2026-06-04T00:00:03Z",
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
        updated_at: "2026-06-04T00:00:03Z",
      },
    ])
  })

  it("deletes an existing AgentCore session", async () => {
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
    expect(result.current.sidebar.projectConversations.get(project.id)).toEqual([])
  })

  it("selects a conversation, persists it, and navigates to the agent page", async () => {
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
    expect(window.localStorage.getItem("bioinfoflow:agent-core-session:project-1")).toBe("session-9")
    expect(pushMock).toHaveBeenCalledWith("/agent")
  })

  it("updates sidebar conversation titles when the active chat emits a title refresh", async () => {
    const apiProjects: Project[] = [{ id: "project-1", name: "Alpha", project_root: "asset://project" }]
    const conversations: AgentCoreSession[] = [
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
      emitAgentSessionUpdated({
        id: "session-1",
        project_id: "project-1",
        title: "RNA-seq QC Plan",
        created_at: "2026-06-04T00:00:00Z",
        updated_at: "2026-06-04T00:00:03Z",
      })
    })

    await waitFor(() =>
      expect(result.current.project.activeConversationTitle).toBe("RNA-seq QC Plan")
    )
  })
})
