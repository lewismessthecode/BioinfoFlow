import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { createAppWrapper } from "@/tests/app-test-utils"
import { useAgentCore } from "@/hooks/use-agent-core"
import { apiRequest } from "@/lib/api"

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
    getApiErrorMessage: actual.getApiErrorMessage,
  }
})

describe("useAgentCore", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const session = (overrides: Record<string, unknown> = {}) => ({
    id: "session-1",
    project_id: "project-1",
    workspace_id: "workspace-1",
    user_id: "dev",
    title: "Existing analysis",
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
    window.localStorage.clear()
  })

  it("creates sessions and turns through AgentCore APIs without using legacy message endpoint", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/sessions" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/memories" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/sessions" && options?.method === "POST") {
        return {
          data: {
            id: "session-1",
            project_id: "project-1",
            workspace_id: "workspace-1",
            user_id: "dev",
            title: "New analysis",
            role_profile: "bioinformatician",
            permission_mode: "guarded_auto",
            automation_mode: "assisted",
            default_model_profile_id: null,
            status: "active",
            metadata: null,
            created_at: "2026-06-04T00:00:00Z",
            updated_at: "2026-06-04T00:00:00Z",
          },
          meta: undefined,
        }
      }
      if (path === "/agent/sessions/session-1/turns" && options?.method === "POST") {
        return {
          data: {
            id: "turn-1",
            session_id: "session-1",
            project_id: "project-1",
            workspace_id: "workspace-1",
            user_id: "dev",
            input_text: "Check FASTQ quality",
            input_parts: null,
            status: "completed",
            model_profile_snapshot: null,
            final_text: "AgentCore session is active.",
            token_usage: null,
            error_code: null,
            error_message: null,
            created_at: "2026-06-04T00:00:01Z",
            updated_at: "2026-06-04T00:00:01Z",
            started_at: "2026-06-04T00:00:01Z",
            completed_at: "2026-06-04T00:00:02Z",
          },
          meta: undefined,
        }
      }
      if (path === "/agent/turns/turn-1/events") {
        return {
          data: [
            {
              id: "event-1",
              session_id: "session-1",
              turn_id: "turn-1",
              seq: 1,
              type: "turn.created",
              payload: { input_text: "Check FASTQ quality" },
              visibility: "user",
              schema_version: 1,
              created_at: "2026-06-04T00:00:01Z",
              updated_at: "2026-06-04T00:00:01Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/turns/turn-1/artifacts") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
    })
    const { result } = renderHook(() => useAgentCore("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.sendTurn("Check FASTQ quality")
    })

    expect(result.current.activeSession?.id).toBe("session-1")
    expect(result.current.turns[0].id).toBe("turn-1")
    expect(result.current.events[0].type).toBe("turn.created")
    expect(apiRequestMock.mock.calls.some(([path]) => path === "/agent/message")).toBe(false)
  })

  it("loads artifacts and memory proposals and dispatches AgentCore decisions", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/sessions" && !options?.method) {
        return {
          data: [
            {
              id: "session-1",
              project_id: "project-1",
              workspace_id: "workspace-1",
              user_id: "dev",
              title: "Existing analysis",
              role_profile: "bioinformatician",
              permission_mode: "guarded_auto",
              automation_mode: "assisted",
              default_model_profile_id: null,
              status: "active",
              metadata: null,
              created_at: "2026-06-04T00:00:00Z",
              updated_at: "2026-06-04T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/sessions/session-1/turns" && !options?.method) {
        return {
          data: [
            {
              id: "turn-1",
              session_id: "session-1",
              project_id: "project-1",
              workspace_id: "workspace-1",
              user_id: "dev",
              input_text: "Check FASTQ quality",
              input_parts: null,
              status: "waiting_approval",
              model_profile_snapshot: null,
              final_text: null,
              token_usage: null,
              error_code: null,
              error_message: null,
              created_at: "2026-06-04T00:00:01Z",
              updated_at: "2026-06-04T00:00:01Z",
              started_at: "2026-06-04T00:00:01Z",
              completed_at: null,
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/turns/turn-1/events" && !options?.method) {
        return {
          data: [
            {
              id: "event-1",
              session_id: "session-1",
              turn_id: "turn-1",
              seq: 1,
              type: "action.waiting_decision",
              payload: {
                action_id: "action-1",
                name: "execution.shell",
                risk_level: "act_high",
              },
              visibility: "user",
              schema_version: 1,
              created_at: "2026-06-04T00:00:02Z",
              updated_at: "2026-06-04T00:00:02Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/turns/turn-1/artifacts" && !options?.method) {
        return {
          data: [
            {
              id: "artifact-1",
              session_id: "session-1",
              turn_id: "turn-1",
              action_id: "action-1",
              type: "log_summary",
              title: "execution.shell output",
              summary: "Command exited with code 0.",
              payload: null,
              file_path: null,
              resource_ref: null,
              created_at: "2026-06-04T00:00:03Z",
              updated_at: "2026-06-04T00:00:03Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/memories" && !options?.method) {
        return {
          data: [
            {
              id: "memory-1",
              workspace_id: "workspace-1",
              project_id: "project-1",
              session_id: "session-1",
              scope: "project",
              type: "project_convention",
              content: { reference_genome: "hg38" },
              source: { turn_id: "turn-1" },
              confidence: 91,
              status: "proposed",
              created_at: "2026-06-04T00:00:04Z",
              updated_at: "2026-06-04T00:00:04Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/agent/actions/action-1/decision" && options?.method === "POST") {
        return {
          data: {
            id: "action-1",
            session_id: "session-1",
            turn_id: "turn-1",
            kind: "tool",
            name: "execution.shell",
            input: {},
            risk_level: "act_high",
            status: "completed",
            created_at: "2026-06-04T00:00:02Z",
            updated_at: "2026-06-04T00:00:05Z",
          },
          meta: undefined,
        }
      }
      if (
        (path === "/agent/memories/memory-1/accept" ||
          path === "/agent/memories/memory-1/reject") &&
        options?.method === "POST"
      ) {
        return {
          data: {
            id: "memory-1",
            workspace_id: "workspace-1",
            project_id: "project-1",
            session_id: "session-1",
            scope: "project",
            type: "project_convention",
            content: { reference_genome: "hg38" },
            source: { turn_id: "turn-1" },
            confidence: 91,
            status: path.endsWith("/accept") ? "accepted" : "rejected",
            created_at: "2026-06-04T00:00:04Z",
            updated_at: "2026-06-04T00:00:05Z",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
    })
    const { result } = renderHook(() => useAgentCore("project-1"), { wrapper: Wrapper })

    await waitFor(() => expect(result.current.turns).toHaveLength(1))
    await waitFor(() => expect(result.current.proposedMemories).toHaveLength(1))

    expect(result.current.events[0].type).toBe("action.waiting_decision")
    expect(result.current.artifactsByTurn.get("turn-1")?.[0]?.title).toBe(
      "execution.shell output",
    )
    expect(result.current.proposedMemories[0]?.type).toBe("project_convention")

    await act(async () => {
      await result.current.approveAction("action-1")
      await result.current.rejectAction("action-1")
      await result.current.acceptMemory("memory-1")
      await result.current.rejectMemory("memory-1")
    })

    expect(
      apiRequestMock.mock.calls.filter(
        ([path]) => path === "/agent/actions/action-1/decision",
      ),
    ).toHaveLength(2)
    expect(
      apiRequestMock.mock.calls.some(
        ([path]) => path === "/agent/memories/memory-1/accept",
      ),
    ).toBe(true)
    expect(
      apiRequestMock.mock.calls.some(
        ([path]) => path === "/agent/memories/memory-1/reject",
      ),
    ).toBe(true)
  })

  it("keeps a controlled draft selected until the first message creates a session", async () => {
    const onActiveSessionIdChange = vi.fn()
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/sessions" && !options?.method) {
        return { data: [session({ id: "session-existing" })], meta: undefined }
      }
      if (path === "/agent/memories" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/sessions" && options?.method === "POST") {
        return {
          data: session({
            id: "session-created",
            title: "New analysis",
            permission_mode: "ask_each_action",
            default_model_profile_id: "profile-1",
          }),
          meta: undefined,
        }
      }
      if (path === "/agent/sessions/session-created/turns" && options?.method === "POST") {
        return {
          data: {
            id: "turn-created",
            session_id: "session-created",
            project_id: "project-1",
            workspace_id: "workspace-1",
            user_id: "dev",
            input_text: "Draft run",
            input_parts: null,
            status: "completed",
            model_profile_snapshot: null,
            final_text: "Ready.",
            token_usage: null,
            error_code: null,
            error_message: null,
            created_at: "2026-06-04T00:00:01Z",
            updated_at: "2026-06-04T00:00:01Z",
            started_at: null,
            completed_at: null,
          },
          meta: undefined,
        }
      }
      if (path === "/agent/turns/turn-created/events") {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/turns/turn-created/artifacts") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
    })
    const { result } = renderHook(
      () =>
        useAgentCore("project-1", {
          activeSessionId: "",
          onActiveSessionIdChange,
        }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.activeSession).toBeNull()
    expect(
      apiRequestMock.mock.calls.some(
        ([path]) => path === "/agent/sessions/session-existing/turns",
      ),
    ).toBe(false)

    act(() => {
      result.current.updateSessionSettings({
        permissionMode: "ask_each_action",
        defaultModelProfileId: "profile-1",
      })
    })
    await act(async () => {
      await result.current.sendTurn("Draft run")
    })

    const createSessionCall = apiRequestMock.mock.calls.find(
      ([path, options]) => path === "/agent/sessions" && options?.method === "POST",
    )
    expect(JSON.parse(createSessionCall?.[1]?.body as string)).toMatchObject({
      project_id: "project-1",
      permission_mode: "ask_each_action",
      default_model_profile_id: "profile-1",
    })
    expect(onActiveSessionIdChange).toHaveBeenCalledWith("session-created")
  })

  it("patches persisted session settings instead of writing draft storage", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/sessions" && !options?.method) {
        return { data: [session()], meta: undefined }
      }
      if (path === "/agent/sessions/session-1/turns" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/memories" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/sessions/session-1" && options?.method === "PATCH") {
        return {
          data: session({
            permission_mode: "bypass",
            default_model_profile_id: "profile-2",
          }),
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
    })
    const { result } = renderHook(
      () => useAgentCore("project-1", { activeSessionId: "session-1" }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.activeSession?.id).toBe("session-1"))
    await act(async () => {
      await result.current.updateSessionSettings({
        permissionMode: "bypass",
        defaultModelProfileId: "profile-2",
      })
    })

    expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1", {
      method: "PATCH",
      body: JSON.stringify({
        permission_mode: "bypass",
        default_model_profile_id: "profile-2",
      }),
    })
    expect(result.current.activePermissionMode).toBe("bypass")
    expect(result.current.activeModelProfileId).toBe("profile-2")
  })

  it("persists selected model metadata for a draft session before the first message", async () => {
    const onActiveSessionIdChange = vi.fn()
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/sessions" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/memories" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/sessions" && options?.method === "POST") {
        return {
          data: session({
            id: "session-created",
            title: "New analysis",
            metadata: { selected_model: "gpt-5.4" },
          }),
          meta: undefined,
        }
      }
      if (path === "/agent/sessions/session-created/turns" && options?.method === "POST") {
        return {
          data: {
            id: "turn-created",
            session_id: "session-created",
            project_id: "project-1",
            workspace_id: "workspace-1",
            user_id: "dev",
            input_text: "Draft run",
            input_parts: null,
            status: "completed",
            model_profile_snapshot: null,
            final_text: "Ready.",
            token_usage: null,
            error_code: null,
            error_message: null,
            created_at: "2026-06-04T00:00:01Z",
            updated_at: "2026-06-04T00:00:01Z",
            started_at: null,
            completed_at: null,
          },
          meta: undefined,
        }
      }
      if (path === "/agent/turns/turn-created/events") {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/turns/turn-created/artifacts") {
        return { data: [], meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
    })
    const { result } = renderHook(
      () =>
        useAgentCore("project-1", {
          activeSessionId: "",
          onActiveSessionIdChange,
        }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.updateSessionSettings({
        modelSelection: { provider: "openai", model: "gpt-5.4" },
      })
    })
    await act(async () => {
      await result.current.sendTurn("Draft run")
    })

    const createSessionCall = apiRequestMock.mock.calls.find(
      ([path, options]) => path === "/agent/sessions" && options?.method === "POST",
    )
    expect(JSON.parse(createSessionCall?.[1]?.body as string)).toMatchObject({
      model_selection: { provider: "openai", model: "gpt-5.4" },
    })
    expect(onActiveSessionIdChange).toHaveBeenCalledWith("session-created")
  })

  it("patches selected model metadata onto an existing session", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/agent/sessions" && !options?.method) {
        return {
          data: [session({ metadata: { selected_model: "gpt-4o-mini" } })],
          meta: undefined,
        }
      }
      if (path === "/agent/sessions/session-1/turns" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/memories" && !options?.method) {
        return { data: [], meta: undefined }
      }
      if (path === "/agent/sessions/session-1" && options?.method === "PATCH") {
        return {
          data: session({
            metadata: { selected_model: "gpt-5.4" },
          }),
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

    const Wrapper = createAppWrapper({
      activeProjectId: "project-1",
      selectedProjectId: "project-1",
    })
    const { result } = renderHook(
      () => useAgentCore("project-1", { activeSessionId: "session-1" }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.activeSession?.id).toBe("session-1"))
    await act(async () => {
      await result.current.updateSessionSettings({
        metadata: { selected_model: "gpt-5.4" },
      })
    })

    expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1", {
      method: "PATCH",
      body: JSON.stringify({
        metadata: { selected_model: "gpt-5.4" },
      }),
    })
    expect(result.current.activeSession?.metadata).toEqual({
      selected_model: "gpt-5.4",
    })
  })
})
