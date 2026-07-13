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
  interruptAgentRuntimeTurn: vi.fn(),
  subscribeAgentRuntimeEvents: vi.fn(),
  getAgentRuntimeState: vi.fn(),
  listAgentRuntimeSessions: vi.fn(),
  updateAgentRuntimeSessionMetadata: vi.fn(),
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
    interruptAgentRuntimeTurn: mocks.interruptAgentRuntimeTurn,
    listAgentRuntimeSessions: mocks.listAgentRuntimeSessions,
    subscribeAgentRuntimeEvents: mocks.subscribeAgentRuntimeEvents,
    updateAgentRuntimeSessionMetadata: mocks.updateAgentRuntimeSessionMetadata,
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
    mocks.updateAgentRuntimeSessionMetadata.mockResolvedValue(session)
    mocks.updateAgentRuntimeSessionPermissionMode.mockResolvedValue(session)
    mocks.interruptAgentRuntimeTurn.mockResolvedValue({
      ...turn,
      status: "cancelled",
    })
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

  it("refreshes state when terminal stream events can carry persisted token usage", async () => {
    renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.subscribeAgentRuntimeEvents).toHaveBeenCalledTimes(1))
    const callsBeforeEvent = mocks.getAgentRuntimeState.mock.calls.length
    const subscription = mocks.subscribeAgentRuntimeEvents.mock.calls[0][0]

    act(() => {
      subscription.onEvent({
        ...event,
        id: "event-completed",
        seq: 2,
        type: "turn.completed",
      })
    })

    await waitFor(() =>
      expect(mocks.getAgentRuntimeState.mock.calls.length).toBeGreaterThan(
        callsBeforeEvent,
      ),
    )
  })

  it("ignores older state refreshes that resolve after a newer token usage refresh", async () => {
    let resolveInitialState: (payload: {
      session: AgentRuntimeSession
      turns: AgentRuntimeTurn[]
      events: AgentRuntimeEvent[]
    }) => void
    let resolveReadyRefresh: (payload: {
      session: AgentRuntimeSession
      turns: AgentRuntimeTurn[]
      events: AgentRuntimeEvent[]
    }) => void
    let resolveTerminalRefresh: (payload: {
      session: AgentRuntimeSession
      turns: AgentRuntimeTurn[]
      events: AgentRuntimeEvent[]
    }) => void
    mocks.getAgentRuntimeState
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveInitialState = resolve
        }),
      )
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveReadyRefresh = resolve
        }),
      )
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveTerminalRefresh = resolve
        }),
      )
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalledTimes(1))
    await act(async () => {
      resolveInitialState({ session, turns: [], events: [] })
    })
    await waitFor(() => expect(mocks.subscribeAgentRuntimeEvents).toHaveBeenCalledTimes(1))
    const subscription = mocks.subscribeAgentRuntimeEvents.mock.calls[0][0]

    await act(async () => {
      subscription.onReady?.()
    })
    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalledTimes(2))

    act(() => {
      subscription.onEvent({
        ...event,
        id: "event-completed",
        seq: 2,
        type: "turn.completed",
      })
    })
    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalledTimes(3))

    await act(async () => {
      resolveTerminalRefresh({
        session: {
          ...session,
          token_usage_summary: {
            has_token_usage: true,
            input_tokens: 90,
            output_tokens: 10,
            total_tokens: 100,
            turns_with_usage: 1,
            raw_totals: {},
          },
        },
        turns: [],
        events: [],
      })
    })
    await waitFor(() =>
      expect(result.current.state.session?.token_usage_summary?.total_tokens).toBe(100),
    )

    await act(async () => {
      resolveReadyRefresh({ session, turns: [], events: [] })
    })

    expect(result.current.state.session?.token_usage_summary?.total_tokens).toBe(100)
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
        activeSkillNames: ["nextflow-debugging"],
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
        activeSkillNames: ["nextflow-debugging"],
      }),
    )
  })

  it("stores the selected remote connection on newly created session metadata", async () => {
    mocks.createAgentRuntimeSession.mockResolvedValue({
      ...session,
      metadata: { remote_connection_id: "connection-1" },
    })
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await act(async () => {
      await result.current.send("hello", {
        remoteConnectionId: "connection-1",
      })
    })

    expect(mocks.createAgentRuntimeSession).toHaveBeenCalledWith(
      expect.objectContaining({
        metadata: { remote_connection_id: "connection-1" },
        executionTarget: expect.objectContaining({
          kind: "remote_ssh",
          type: "remote_ssh",
          remote_connection_id: "connection-1",
          connection_id: "connection-1",
        }),
      }),
    )
    expect(mocks.createAgentRuntimeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        executionTarget: expect.objectContaining({
          kind: "remote_ssh",
          type: "remote_ssh",
          remote_connection_id: "connection-1",
          connection_id: "connection-1",
        }),
      }),
    )
  })

  it("preserves backend-provided remote metadata when no remote override is sent", async () => {
    mocks.createAgentRuntimeSession.mockResolvedValue({
      ...session,
      metadata: { remote_connection_id: "project-default-connection" },
    })
    const { result } = renderHook(() =>
      useAgentRuntime("remote-project-1", {
        activeSessionId: "",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await act(async () => {
      await result.current.send("hello")
    })

    expect(mocks.createAgentRuntimeSession).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: "remote-project-1",
        metadata: undefined,
      }),
    )
    expect(mocks.updateAgentRuntimeSessionMetadata).not.toHaveBeenCalled()
  })

  it("updates existing session metadata before sending with a new remote connection", async () => {
    const updatedSession = {
      ...session,
      metadata: { remote_connection_id: "connection-2" },
      updated_at: "2026-06-08T00:00:03Z",
    }
    mocks.listAgentRuntimeSessions.mockResolvedValue([
      { ...session, metadata: { remote_connection_id: "connection-1" } },
    ])
    mocks.getAgentRuntimeState.mockResolvedValue({
      session: { ...session, metadata: { remote_connection_id: "connection-1" } },
      turns: [],
      events: [],
    })
    mocks.updateAgentRuntimeSessionMetadata.mockResolvedValue(updatedSession)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalled())

    await act(async () => {
      await result.current.send("hello", {
        remoteConnectionId: "connection-2",
      })
    })

    expect(mocks.updateAgentRuntimeSessionMetadata).toHaveBeenCalledWith(
      "session-1",
      { remote_connection_id: "connection-2" },
      expect.objectContaining({
        kind: "remote_ssh",
        type: "remote_ssh",
        remote_connection_id: "connection-2",
        connection_id: "connection-2",
      }),
    )
    expect(mocks.createAgentRuntimeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: "session-1",
        executionTarget: expect.objectContaining({
          kind: "remote_ssh",
          type: "remote_ssh",
          remote_connection_id: "connection-2",
          connection_id: "connection-2",
        }),
      }),
    )
  })

  it("clears stale remote connection metadata before sending without a selection", async () => {
    const updatedSession = {
      ...session,
      metadata: { batch: "b001" },
      updated_at: "2026-06-08T00:00:03Z",
    }
    mocks.listAgentRuntimeSessions.mockResolvedValue([
      {
        ...session,
        metadata: { batch: "b001", remote_connection_id: "connection-1" },
        execution_target: {
          type: "remote_ssh",
          connection_id: "connection-1",
        },
      },
    ])
    mocks.getAgentRuntimeState.mockResolvedValue({
      session: {
        ...session,
        metadata: { batch: "b001", remote_connection_id: "connection-1" },
        execution_target: {
          type: "remote_ssh",
          connection_id: "connection-1",
        },
      },
      turns: [],
      events: [],
    })
    mocks.updateAgentRuntimeSessionMetadata.mockResolvedValue(updatedSession)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalled())

    await act(async () => {
      await result.current.send("hello", {
        remoteConnectionId: null,
      })
    })

    expect(mocks.updateAgentRuntimeSessionMetadata).toHaveBeenCalledWith(
      "session-1",
      { batch: "b001" },
      expect.objectContaining({
        kind: "local",
        type: "local",
      }),
    )
    expect(mocks.createAgentRuntimeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        executionTarget: expect.objectContaining({
          kind: "local",
          type: "local",
        }),
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

  it("optimistically patches permission mode and exposes authoritative reconciliation", async () => {
    const request = deferred<AgentRuntimeSession>()
    const updated = {
      ...session,
      permission_mode: "bypass" as const,
      permission_policy_version: 2,
      pending_strategy: "approve_pending_tools" as const,
      pending_reconciliation: {
        affected_count: 2,
        excluded_count: 1,
        already_resolved_count: 1,
      },
    }
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(mocks.getAgentRuntimeState).toHaveBeenCalled())
    let updatePromise!: Promise<AgentRuntimeSession | null>
    act(() => {
      updatePromise = result.current.setPermissionMode(
        "bypass",
        "approve_pending_tools",
      )
    })

    expect(result.current.permissionMode).toBe("bypass")
    expect(result.current.session?.permission_mode).toBe("bypass")
    expect(result.current.permissionUpdate.status).toBe("pending")
    expect(
      window.localStorage.getItem("bioinfoflow.agentRuntime.permissionMode:v2"),
    ).toBe("bypass")

    await act(async () => {
      request.resolve(updated)
      await updatePromise
    })

    expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledWith(
      "session-1",
      "bypass",
      "approve_pending_tools",
    )
    expect(result.current.permissionUpdate).toMatchObject({
      status: "success",
      mode: "bypass",
      reconciliation: updated.pending_reconciliation,
    })
  })

  it("restores the exact session, draft, and storage snapshot after a failed update", async () => {
    window.localStorage.setItem(
      "bioinfoflow.agentRuntime.permissionMode:v2",
      "guarded_auto",
    )
    mocks.updateAgentRuntimeSessionPermissionMode.mockRejectedValue(
      new Error("Permission service unavailable"),
    )
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    await act(async () => {
      await result.current.setPermissionMode("bypass")
    })

    expect(result.current.permissionMode).toBe("guarded_auto")
    expect(result.current.session).toMatchObject(session)
    expect(
      window.localStorage.getItem("bioinfoflow.agentRuntime.permissionMode:v2"),
    ).toBe("guarded_auto")
    expect(result.current.permissionUpdate).toMatchObject({
      status: "error",
      mode: "bypass",
      error: "Permission service unavailable",
    })
  })

  it("captures an authoritative rollback snapshot before the initial loading effects settle", async () => {
    const sessionList = deferred<AgentRuntimeSession[]>()
    const permissionRequest = deferred<AgentRuntimeSession>()
    window.localStorage.setItem(
      "bioinfoflow.agentRuntime.permissionMode:v2",
      "guarded_auto",
    )
    mocks.listAgentRuntimeSessions.mockReturnValue(sessionList.promise)
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(
      permissionRequest.promise,
    )

    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.state.session?.id).toBe("session-1"))
    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })

    expect(result.current.session?.permission_mode).toBe("bypass")
    expect(result.current.sessions).toContainEqual(
      expect.objectContaining({ id: "session-1", permission_mode: "bypass" }),
    )

    await act(async () => {
      permissionRequest.reject(new Error("Permission service unavailable"))
      await update
    })

    expect(result.current.permissionUpdate.status).toBe("error")

    expect(result.current.permissionMode).toBe("guarded_auto")
    expect(result.current.session).toMatchObject({
      id: "session-1",
      permission_mode: "guarded_auto",
    })
    expect(result.current.state.session).toMatchObject({
      id: "session-1",
      permission_mode: "guarded_auto",
    })
    expect(
      window.localStorage.getItem("bioinfoflow.agentRuntime.permissionMode:v2"),
    ).toBe("guarded_auto")
  })

  it("rolls back only policy fields when same-version state refreshes add a newer title", async () => {
    const request = deferred<AgentRuntimeSession>()
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })

    mocks.getAgentRuntimeState.mockResolvedValue({
      session: {
        ...session,
        title: "New server title",
        updated_at: "2026-06-08T00:00:05Z",
      },
      turns: [],
      events: [],
    })
    await act(async () => {
      await result.current.refreshState("session-1")
      request.reject(new Error("Permission service unavailable"))
      await update
    })

    expect(result.current.session).toMatchObject({
      title: "New server title",
      updated_at: "2026-06-08T00:00:05Z",
      permission_mode: "guarded_auto",
    })
    expect(result.current.state.session).toMatchObject({
      title: "New server title",
      permission_mode: "guarded_auto",
    })
  })

  it("suppresses duplicate permission requests and retries the failed transaction", async () => {
    const request = deferred<AgentRuntimeSession>()
    mocks.updateAgentRuntimeSessionPermissionMode
      .mockReturnValueOnce(request.promise)
      .mockResolvedValueOnce({
        ...session,
        permission_mode: "bypass",
        permission_policy_version: 2,
      })
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let first!: Promise<AgentRuntimeSession | null>
    let duplicate!: Promise<AgentRuntimeSession | null>
    act(() => {
      first = result.current.setPermissionMode("bypass")
      duplicate = result.current.setPermissionMode("bypass")
    })

    expect(duplicate).toBe(first)
    await waitFor(() =>
      expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledTimes(1),
    )

    await act(async () => {
      request.reject(new Error("Try again"))
      await first
    })
    await act(async () => {
      await result.current.retryPermissionModeUpdate()
    })

    expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledTimes(2)
    expect(result.current.permissionUpdate.status).toBe("success")
  })

  it("serializes overlapping permission changes and keeps the latest intent", async () => {
    const firstRequest = deferred<AgentRuntimeSession>()
    const secondRequest = deferred<AgentRuntimeSession>()
    mocks.updateAgentRuntimeSessionPermissionMode
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let first!: Promise<AgentRuntimeSession | null>
    let second!: Promise<AgentRuntimeSession | null>
    act(() => {
      first = result.current.setPermissionMode("bypass")
      second = result.current.setPermissionMode("ask_each_action")
    })

    expect(result.current.permissionMode).toBe("ask_each_action")
    await waitFor(() =>
      expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledTimes(1),
    )

    await act(async () => {
      firstRequest.resolve({
        ...session,
        permission_mode: "bypass",
        permission_policy_version: 2,
      })
      await first
    })
    await waitFor(() =>
      expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledTimes(2),
    )
    expect(result.current.permissionMode).toBe("ask_each_action")

    await act(async () => {
      secondRequest.resolve({
        ...session,
        permission_mode: "ask_each_action",
        permission_policy_version: 3,
      })
      await second
    })

    expect(result.current.permissionMode).toBe("ask_each_action")
    expect(result.current.permissionUpdate.status).toBe("success")
  })

  it("does not let an older session success replace a newer confirmed draft", async () => {
    const firstRequest = deferred<AgentRuntimeSession>()
    const session2 = { ...session, id: "session-2" }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.updateAgentRuntimeSessionPermissionMode
      .mockReturnValueOnce(firstRequest.promise)
      .mockRejectedValueOnce(new Error("Session two failed"))
    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let first!: Promise<AgentRuntimeSession | null>
    act(() => {
      first = result.current.setPermissionMode("bypass")
    })

    rerender({ activeSessionId: "" })
    await waitFor(() => expect(result.current.session).toBeNull())
    await act(async () => {
      await result.current.setPermissionMode("ask_each_action")
    })

    await act(async () => {
      firstRequest.resolve({
        ...session,
        permission_mode: "bypass",
        permission_policy_version: 2,
      })
      await first
    })

    mocks.getAgentRuntimeState.mockResolvedValue({ session: session2, turns: [], events: [] })
    rerender({ activeSessionId: "session-2" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-2"))
    await act(async () => {
      await result.current.setPermissionMode("guarded_auto")
    })

    expect(window.localStorage.getItem("bioinfoflow.agentRuntime.permissionMode:v2")).toBe(
      "ask_each_action",
    )
  })

  it("does not apply a completed permission transaction to a newly selected session", async () => {
    const request = deferred<AgentRuntimeSession>()
    const session2 = { ...session, id: "session-2", permission_policy_version: 7 }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })
    mocks.getAgentRuntimeState.mockResolvedValue({
      session: session2,
      turns: [],
      events: [],
    })
    rerender({ activeSessionId: "session-2" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-2"))

    await act(async () => {
      request.resolve({
        ...session,
        permission_mode: "bypass",
        permission_policy_version: 2,
      })
      await update
    })

    expect(result.current.session?.id).toBe("session-2")
    expect(result.current.permissionMode).toBe("guarded_auto")
    expect(result.current.permissionUpdate.status).toBe("idle")
  })

  it("merges an authoritative permission response after switching away and back", async () => {
    const request = deferred<AgentRuntimeSession>()
    const session2 = { ...session, id: "session-2" }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })

    mocks.getAgentRuntimeState.mockResolvedValue({ session: session2, turns: [], events: [] })
    rerender({ activeSessionId: "session-2" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-2"))

    mocks.getAgentRuntimeState.mockResolvedValue({ session, turns: [], events: [] })
    rerender({ activeSessionId: "session-1" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    await act(async () => {
      await result.current.refreshState("session-1")
    })
    expect(result.current.session?.permission_policy_version ?? 0).toBeLessThan(2)

    await act(async () => {
      request.resolve({
        ...session,
        permission_mode: "bypass",
        permission_policy_version: 2,
      })
      await update
    })

    expect(result.current.session).toMatchObject({
      id: "session-1",
      permission_mode: "bypass",
      permission_policy_version: 2,
    })
    expect(result.current.permissionUpdate.status).toBe("idle")
  })

  it("does not surface a failed permission transaction on a newly selected session", async () => {
    const request = deferred<AgentRuntimeSession>()
    const session2 = { ...session, id: "session-2", permission_policy_version: 7 }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })
    mocks.getAgentRuntimeState.mockResolvedValue({ session: session2, turns: [], events: [] })
    rerender({ activeSessionId: "session-2" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-2"))

    await act(async () => {
      request.reject(new Error("Session one failed"))
      await update
    })

    expect(result.current.permissionUpdate.status).toBe("idle")
    expect(result.current.permissionUpdate.error).toBeNull()
  })

  it("does not retry a failed permission transaction after its session becomes inactive", async () => {
    const session2 = { ...session, id: "session-2", permission_policy_version: 7 }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.updateAgentRuntimeSessionPermissionMode.mockRejectedValue(
      new Error("Session one failed"),
    )
    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, {
          activeSessionId,
          onActiveSessionIdChange: vi.fn(),
        }),
      { initialProps: { activeSessionId: "session-1" } },
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    await act(async () => {
      await result.current.setPermissionMode("bypass")
    })
    mocks.getAgentRuntimeState.mockResolvedValue({ session: session2, turns: [], events: [] })
    rerender({ activeSessionId: "session-2" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-2"))

    await act(async () => {
      await result.current.retryPermissionModeUpdate()
    })

    expect(mocks.updateAgentRuntimeSessionPermissionMode).toHaveBeenCalledTimes(1)
    expect(mocks.updateAgentRuntimeSessionPermissionMode).not.toHaveBeenCalledWith(
      "session-2",
      expect.anything(),
      expect.anything(),
    )
  })

  it("does not replace a newer permission policy with a stale session list response", async () => {
    const sessionList = deferred<AgentRuntimeSession[]>()
    const newest = {
      ...session,
      permission_mode: "bypass" as const,
      permission_policy_version: 5,
    }
    mocks.listAgentRuntimeSessions.mockReturnValue(sessionList.promise)
    mocks.getAgentRuntimeState.mockResolvedValue({ session: newest, turns: [], events: [] })
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.session?.permission_policy_version).toBe(5))
    await act(async () => {
      sessionList.resolve([{ ...session, permission_policy_version: 4 }])
      await sessionList.promise
    })

    expect(result.current.session?.permission_policy_version).toBe(5)
    expect(result.current.permissionMode).toBe("bypass")
  })

  it("does not replace a newer policy version with a stale patch response", async () => {
    const newest = { ...session, permission_policy_version: 5 }
    mocks.listAgentRuntimeSessions.mockResolvedValue([newest])
    mocks.getAgentRuntimeState.mockResolvedValue({ session: newest, turns: [], events: [] })
    mocks.updateAgentRuntimeSessionPermissionMode.mockResolvedValue({
      ...session,
      permission_mode: "bypass",
      permission_policy_version: 4,
    })
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.session?.permission_policy_version).toBe(5))
    await act(async () => {
      await result.current.setPermissionMode("bypass")
    })

    expect(result.current.session?.permission_policy_version).toBe(5)
    expect(result.current.permissionMode).toBe("guarded_auto")
  })

  it("rejects a patch response superseded by state loaded while the patch is pending", async () => {
    const request = deferred<AgentRuntimeSession>()
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )
    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))

    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })
    const newest = {
      ...session,
      permission_mode: "ask_each_action" as const,
      permission_policy_version: 3,
    }
    mocks.getAgentRuntimeState.mockResolvedValue({ session: newest, turns: [], events: [] })
    await act(async () => {
      await result.current.refreshState("session-1")
      request.resolve({ ...session, permission_mode: "bypass", permission_policy_version: 2 })
      await update
    })

    expect(result.current.permissionMode).toBe("ask_each_action")
    expect(result.current.permissionUpdate.status).toBe("error")
  })

  it("rolls back draft storage when an inactive session permission update fails", async () => {
    const request = deferred<AgentRuntimeSession>()
    const session2 = { ...session, id: "session-2" }
    mocks.listAgentRuntimeSessions.mockResolvedValue([session, session2])
    mocks.updateAgentRuntimeSessionPermissionMode.mockReturnValue(request.promise)
    const { result, rerender } = renderHook(
      ({ activeSessionId }: { activeSessionId: string }) =>
        useAgentRuntime(null, { activeSessionId, onActiveSessionIdChange: vi.fn() }),
      { initialProps: { activeSessionId: "session-1" } },
    )
    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    let update!: Promise<AgentRuntimeSession | null>
    act(() => {
      update = result.current.setPermissionMode("bypass")
    })
    mocks.getAgentRuntimeState.mockResolvedValue({ session: session2, turns: [], events: [] })
    rerender({ activeSessionId: "session-2" })
    await act(async () => {
      request.reject(new Error("failed"))
      await update
    })

    expect(
      window.localStorage.getItem("bioinfoflow.agentRuntime.permissionMode:v2"),
    ).toBeNull()

    mocks.getAgentRuntimeState.mockResolvedValue({ session, turns: [], events: [] })
    rerender({ activeSessionId: "session-1" })
    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    expect(result.current.permissionMode).toBe("guarded_auto")
    expect(result.current.sessions.find((item) => item.id === "session-1")).toMatchObject({
      permission_mode: "guarded_auto",
    })
  })

  it("interrupts paused turns waiting for approval", async () => {
    mocks.getAgentRuntimeState.mockResolvedValue({
      session,
      turns: [{ ...turn, status: "waiting_approval" }],
      events: [],
    })
    const { result } = renderHook(() =>
      useAgentRuntime(null, {
        activeSessionId: "session-1",
        onActiveSessionIdChange: vi.fn(),
      }),
    )

    await waitFor(() => expect(result.current.state.turns[0]?.status).toBe("waiting_approval"))

    await act(async () => {
      await result.current.interrupt()
    })

    expect(mocks.interruptAgentRuntimeTurn).toHaveBeenCalledWith("turn-1")
  })
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}
