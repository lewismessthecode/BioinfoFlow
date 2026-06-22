import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import type {
  AgentRuntimeEvent,
  AgentRuntimeSession,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"

const mocks = vi.hoisted(() => ({
  createAgentRuntimeSession: vi.fn(),
  createAgentRuntimeTurn: vi.fn(),
  subscribeAgentRuntimeEvents: vi.fn(),
  getAgentRuntimeState: vi.fn(),
  listAgentRuntimeSessions: vi.fn(),
  updateAgentRuntimeSessionPermissionMode: vi.fn(),
}))

vi.mock("@/lib/runtime", () => ({
  getCurrentRuntime: () => ({ mode: "live" }),
}))

vi.mock("@/lib/agent-runtime", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/agent-runtime")>()
  return {
    ...actual,
    createAgentRuntimeSession: mocks.createAgentRuntimeSession,
    createAgentRuntimeTurn: mocks.createAgentRuntimeTurn,
    decideAgentRuntimeAction: vi.fn(),
    getAgentRuntimeState: mocks.getAgentRuntimeState,
    interruptAgentRuntimeTurn: vi.fn(),
    listAgentRuntimeSessions: mocks.listAgentRuntimeSessions,
    subscribeAgentRuntimeEvents: mocks.subscribeAgentRuntimeEvents,
    updateAgentRuntimeSessionPermissionMode: mocks.updateAgentRuntimeSessionPermissionMode,
  }
})

const session: AgentRuntimeSession = {
  id: "session-1",
  workspace_id: "workspace-1",
  user_id: "dev",
  role_profile: "bioinformatician",
  permission_mode: "guarded_auto",
  automation_mode: "assisted",
  runtime_mode: "api",
  status: "active",
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z",
}

const event: AgentRuntimeEvent = {
  id: "event-1",
  session_id: "session-1",
  turn_id: "turn-1",
  seq: 1,
  type: "turn.created",
  payload: {},
  visibility: "user",
  schema_version: 1,
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z",
}

const turn: AgentRuntimeTurn = {
  id: "turn-1",
  session_id: "session-1",
  project_id: null,
  workspace_id: "workspace-1",
  user_id: "dev",
  input_text: "hello",
  status: "completed",
  iteration_count: 1,
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z",
}

describe("useAgentRuntime", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    mocks.listAgentRuntimeSessions.mockResolvedValue([session])
    mocks.getAgentRuntimeState.mockResolvedValue({ session, turns: [], events: [] })
    mocks.subscribeAgentRuntimeEvents.mockReturnValue(vi.fn())
    mocks.createAgentRuntimeSession.mockResolvedValue(session)
    mocks.createAgentRuntimeTurn.mockResolvedValue({
      id: "turn-1",
      session_id: "session-1",
      project_id: null,
      workspace_id: "workspace-1",
      user_id: "dev",
      input_text: "hello",
      status: "queued",
      iteration_count: 0,
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z",
    })
    mocks.updateAgentRuntimeSessionPermissionMode.mockResolvedValue(session)
  })

  it("does not recreate the SSE subscription for each received event", async () => {
    renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.subscribeAgentRuntimeEvents).toHaveBeenCalledTimes(1))
    const subscription = mocks.subscribeAgentRuntimeEvents.mock.calls[0][0]

    act(() => {
      subscription.onEvent(event)
    })

    await waitFor(() => expect(mocks.subscribeAgentRuntimeEvents).toHaveBeenCalledTimes(1))
  })

  it("exposes stream status and refreshes state when the stream is ready", async () => {
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.subscribeAgentRuntimeEvents).toHaveBeenCalledTimes(1))
    const stateCallsBeforeReady = mocks.getAgentRuntimeState.mock.calls.length
    const subscription = mocks.subscribeAgentRuntimeEvents.mock.calls[0][0]

    expect(result.current.streamStatus).toBe("connecting")

    await act(async () => {
      subscription.onReady?.()
    })

    expect(result.current.streamStatus).toBe("connected")
    expect(mocks.getAgentRuntimeState.mock.calls.length).toBeGreaterThan(
      stateCallsBeforeReady,
    )
  })

  it("keeps a controlled empty session as a draft conversation", async () => {
    const onActiveSessionIdChange = vi.fn()

    renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "",
        onActiveSessionIdChange,
      }),
    )

    await waitFor(() => expect(mocks.listAgentRuntimeSessions).toHaveBeenCalled())

    expect(onActiveSessionIdChange).not.toHaveBeenCalledWith("session-1")
    expect(mocks.getAgentRuntimeState).not.toHaveBeenCalled()
    expect(mocks.subscribeAgentRuntimeEvents).not.toHaveBeenCalled()
  })

  it("uses the stored draft permission mode when creating a session", async () => {
    window.localStorage.setItem("bioinfoflow.agentRuntime.permissionMode", "bypass")
    const onActiveSessionIdChange = vi.fn()
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "",
        onActiveSessionIdChange,
      }),
    )

    await act(async () => {
      await result.current.send("hello", {
        inputParts: [
          { type: "text", text: "hello" },
          { kind: "file_ref", path: "/workspace/workflow.wdl", label: "workflow.wdl" },
        ],
      })
    })

    expect(mocks.createAgentRuntimeSession).toHaveBeenCalledWith(
      expect.objectContaining({ permissionMode: "bypass" }),
    )
    expect(mocks.createAgentRuntimeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        inputParts: [
          { type: "text", text: "hello" },
          { kind: "file_ref", path: "/workspace/workflow.wdl", label: "workflow.wdl" },
        ],
      }),
    )
  })

  it("merges refreshed session titles into the session list", async () => {
    mocks.getAgentRuntimeState.mockResolvedValue({
      session: {
        ...session,
        title: "RNA-seq QC Plan",
        updated_at: "2026-06-08T00:00:02Z",
      },
      turns: [],
      events: [],
    })

    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await act(async () => {
      await result.current.refreshState("session-1")
    })

    expect(result.current.sessions[0]?.title).toBe("RNA-seq QC Plan")
  })

  it("loads complete session state when restoring a conversation", async () => {
    renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() =>
      expect(mocks.getAgentRuntimeState).toHaveBeenCalledWith("session-1"),
    )
  })

  it("starts the live stream after state load from the latest loaded event", async () => {
    let resolveState: (payload: {
      session: AgentRuntimeSession
      turns: AgentRuntimeTurn[]
      events: AgentRuntimeEvent[]
    }) => void
    mocks.getAgentRuntimeState.mockReturnValue(
      new Promise((resolve) => {
        resolveState = resolve
      }),
    )

    renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalled())
    expect(mocks.subscribeAgentRuntimeEvents).not.toHaveBeenCalled()

    await act(async () => {
      resolveState({
        session,
        turns: [],
        events: [
          { ...event, id: "event-499", seq: 499 },
          { ...event, id: "event-500", seq: 500 },
        ],
      })
    })

    await waitFor(() =>
      expect(mocks.subscribeAgentRuntimeEvents).toHaveBeenCalledWith(
        expect.objectContaining({
          sessionId: "session-1",
          afterSeq: 500,
        }),
      ),
    )
  })

  it("does not mark restored state as a limited event window", async () => {
    mocks.getAgentRuntimeState.mockResolvedValue({
      session,
      turns: [],
      events: Array.from({ length: 500 }, (_, index) => ({
        ...event,
        id: `event-${index + 1}`,
        seq: index + 1,
      })),
    })

    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.eventWindowLimited).toBe(false))
  })

  it("treats refreshed session lists as authoritative when a title is cleared", async () => {
    mocks.listAgentRuntimeSessions.mockResolvedValue([{ ...session, title: "Old title" }])
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.sessions[0]?.title).toBe("Old title"))

    mocks.listAgentRuntimeSessions.mockResolvedValue([
      { ...session, title: null, updated_at: "2026-06-08T00:00:03Z" },
    ])
    await act(async () => {
      await result.current.refreshSessions()
    })

    expect(result.current.sessions[0]?.title).toBeNull()
  })

  it("ignores stale state refreshes for inactive sessions", async () => {
    const session2: AgentRuntimeSession = { ...session, id: "session-2" }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.getAgentRuntimeState.mockResolvedValue({ session: session2, turns: [], events: [] })
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-2",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.state.session?.id).toBe("session-2"))

    mocks.getAgentRuntimeState.mockResolvedValue({ session, turns: [], events: [] })
    await act(async () => {
      await result.current.refreshState("session-1")
    })

    expect(result.current.state.session?.id).toBe("session-2")
  })

  it("ignores stale state refreshes after returning to a controlled draft", async () => {
    let resolveState: (payload: {
      session: AgentRuntimeSession
      turns: AgentRuntimeTurn[]
      events: AgentRuntimeEvent[]
    }) => void
    mocks.getAgentRuntimeState.mockReturnValue(
      new Promise((resolve) => {
        resolveState = resolve
      }),
    )

    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalledWith("session-1"))

    rerender({ activeSessionId: "" })

    await act(async () => {
      resolveState({ session, turns: [turn], events: [event] })
    })

    expect(result.current.state.session).toBeNull()
    expect(result.current.state.turns).toEqual([])
    expect(result.current.state.events).toEqual([])
  })

  it("clears the previous session state immediately when the active session changes", async () => {
    const session2: AgentRuntimeSession = { ...session, id: "session-2" }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.getAgentRuntimeState.mockResolvedValue({
      session,
      turns: [turn],
      events: [],
    })

    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(result.current.state.turns).toHaveLength(1))

    mocks.getAgentRuntimeState.mockResolvedValue({
      session: session2,
      turns: [],
      events: [],
    })
    rerender({ activeSessionId: "session-2" })

    expect(result.current.state.turns).toEqual([])
    expect(result.current.state.status).toBe("loading")
  })

  it("patches permission mode for existing sessions", async () => {
    const updated = { ...session, permission_mode: "bypass" as const }
    mocks.updateAgentRuntimeSessionPermissionMode.mockResolvedValue(updated)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalled())
    await act(async () => {
      await result.current.setPermissionMode("bypass")
    })

    expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledWith(
      "session-1",
      "bypass",
    )
    expect(window.localStorage.getItem("bioinfoflow.agentRuntime.permissionMode")).toBe(
      "bypass",
    )
  })
})
