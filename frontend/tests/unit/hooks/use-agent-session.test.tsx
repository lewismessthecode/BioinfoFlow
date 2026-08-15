import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type {
  InputPart,
  InteractionResponse,
  SessionSnapshot,
} from "@/lib/agent/contracts"

const mocks = vi.hoisted(() => ({
  dispatchAgentCommand: vi.fn(),
  getAgentSnapshot: vi.fn(),
  updateAgentSession: vi.fn(),
  subscribeAgentEvents: vi.fn(),
  unsubscribe: vi.fn(),
}))

vi.mock("@/lib/agent/client", () => ({
  dispatchAgentCommand: mocks.dispatchAgentCommand,
  getAgentSnapshot: mocks.getAgentSnapshot,
  updateAgentSession: mocks.updateAgentSession,
}))

vi.mock("@/lib/agent/stream", () => ({
  subscribeAgentEvents: mocks.subscribeAgentEvents,
}))

import { useAgentSession } from "@/hooks/use-agent-session"

const timestamp = "2026-08-15T00:00:00Z"

function snapshot(title = "Analysis"): SessionSnapshot {
  return {
    session: {
      id: "session-1",
      user_id: "user-1",
      workspace_id: "workspace-1",
      project_id: "project-1",
      title,
      model: {
        provider: "openai",
        model: "gpt-5.6",
        display_name: "GPT-5.6",
        supports_vision: true,
        supports_reasoning: true,
        supports_tools: true,
      },
      permission_mode: "ask_dangerous",
      workspace_access: "read_write",
      status: "active",
      created_at: timestamp,
      updated_at: timestamp,
    },
    runs: [],
    entries: [],
    active_run: null,
    history_revision: 0,
  }
}

function snapshotFor(sessionId: string, title: string): SessionSnapshot {
  const value = snapshot(title)
  return {
    ...value,
    session: { ...value.session, id: sessionId },
  }
}

function streamingSnapshot(): SessionSnapshot {
  const value = snapshot()
  const run = {
    id: "run-1",
    session_id: "session-1",
    status: "running" as const,
    phase: "model" as const,
    revision: 1,
    started_at: timestamp,
    completed_at: null,
    termination_reason: null,
    error: null,
    created_at: timestamp,
    updated_at: timestamp,
  }
  return {
    ...value,
    runs: [run],
    active_run: {
      run,
      assistant_draft: {
        id: "draft-1",
        run_id: "run-1",
        parts: [{ id: "part-1", type: "text", text: "Hello", end_offset: 5 }],
      },
      tool_progress: [],
      pending_interaction: null,
    },
  }
}

describe("useAgentSession", () => {
  beforeEach(() => {
    mocks.dispatchAgentCommand.mockReset()
    mocks.getAgentSnapshot.mockReset()
    mocks.getAgentSnapshot.mockResolvedValue(snapshot())
    mocks.updateAgentSession.mockReset()
    mocks.subscribeAgentEvents.mockReset()
    mocks.unsubscribe.mockReset()
    mocks.subscribeAgentEvents.mockReturnValue(mocks.unsubscribe)
  })

  it("loads an initial snapshot while subscribing immediately to live events", async () => {
    const { result } = renderHook(() => useAgentSession("session-1"))

    expect(result.current.isLoading).toBe(true)
    expect(result.current.connectionStatus).toBe("connecting")
    expect(mocks.subscribeAgentEvents).toHaveBeenCalledWith({
      sessionId: "session-1",
      onEvent: expect.any(Function),
      onConnectionChange: expect.any(Function),
      onError: expect.any(Function),
    })
    expect(mocks.getAgentSnapshot).toHaveBeenCalledWith("session-1")

    const subscription = mocks.subscribeAgentEvents.mock.calls[0][0]
    act(() => {
      subscription.onEvent({ type: "snapshot", snapshot: snapshot() })
      subscription.onConnectionChange("connected")
    })

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    expect(result.current.isLoading).toBe(false)
    expect(result.current.connectionStatus).toBe("connected")
    expect(result.current.error).toBeNull()
  })

  it("reports a stream interruption and clears it after a recovery snapshot", () => {
    const { result } = renderHook(() => useAgentSession("session-1"))
    const subscription = mocks.subscribeAgentEvents.mock.calls[0][0]

    act(() => {
      subscription.onConnectionChange("reconnecting")
      subscription.onError(new Event("error"))
    })
    expect(result.current.connectionStatus).toBe("reconnecting")
    expect(result.current.error?.message).toBe(
      "Agent event stream disconnected",
    )

    act(() => {
      subscription.onEvent({ type: "snapshot", snapshot: snapshot() })
      subscription.onConnectionChange("connected")
    })
    expect(result.current.connectionStatus).toBe("connected")
    expect(result.current.error).toBeNull()
  })

  it("applies live events and refetches when a delta cannot be reconciled", async () => {
    mocks.getAgentSnapshot
      .mockResolvedValueOnce(snapshot("Initial"))
      .mockResolvedValueOnce(snapshot("Recovered"))

    const { result } = renderHook(() => useAgentSession("session-1"))

    await waitFor(() => expect(mocks.subscribeAgentEvents).toHaveBeenCalled())
    const subscription = mocks.subscribeAgentEvents.mock.calls[0][0]

    act(() => {
      subscription.onEvent({ type: "snapshot", snapshot: streamingSnapshot() })
      subscription.onEvent({
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "part-1",
        part_type: "text",
        start_offset: 5,
        end_offset: 6,
        delta: "!",
      })
    })
    expect(result.current.activeRun?.assistant_draft?.parts[0].text).toBe(
      "Hello!",
    )

    act(() => {
      subscription.onEvent({
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "part-1",
        part_type: "text",
        start_offset: 9,
        end_offset: 10,
        delta: "?",
      })
    })

    await waitFor(() => expect(mocks.getAgentSnapshot).toHaveBeenCalledTimes(2))
    expect(mocks.getAgentSnapshot).toHaveBeenLastCalledWith("session-1")
    await waitFor(() => expect(result.current.session?.title).toBe("Recovered"))
  })

  it("exposes stable actions for the four public commands", async () => {
    mocks.dispatchAgentCommand
      .mockResolvedValueOnce(snapshot("Message sent"))
      .mockResolvedValueOnce(snapshot("Steered"))
      .mockResolvedValueOnce(snapshot("Responded"))
      .mockResolvedValueOnce(snapshot("Cancelled"))
    const parts: InputPart[] = [
      { type: "text", text: "Inspect this workflow" },
    ]
    const response: InteractionResponse = {
      type: "approval",
      approved: true,
    }

    const { result, rerender } = renderHook(() =>
      useAgentSession("session-1"),
    )
    const subscription = mocks.subscribeAgentEvents.mock.calls[0][0]
    act(() => {
      subscription.onEvent({ type: "snapshot", snapshot: snapshot() })
    })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const firstSendMessage = result.current.sendMessage
    rerender()
    expect(result.current.sendMessage).toBe(firstSendMessage)

    await act(async () => {
      await result.current.sendMessage(parts)
      await result.current.steer(parts)
      await result.current.respond("interaction-1", response)
      await result.current.cancel()
    })

    expect(mocks.dispatchAgentCommand).toHaveBeenNthCalledWith(
      1,
      "session-1",
      {
        type: "message",
        command_id: expect.any(String),
        parts,
      },
    )
    expect(mocks.dispatchAgentCommand).toHaveBeenNthCalledWith(
      2,
      "session-1",
      {
        type: "steer",
        command_id: expect.any(String),
        parts,
      },
    )
    expect(mocks.dispatchAgentCommand).toHaveBeenNthCalledWith(
      3,
      "session-1",
      {
        type: "respond",
        command_id: expect.any(String),
        interaction_id: "interaction-1",
        response,
      },
    )
    expect(mocks.dispatchAgentCommand).toHaveBeenNthCalledWith(
      4,
      "session-1",
      {
        type: "cancel",
        command_id: expect.any(String),
      },
    )
    expect(result.current.session?.title).toBe("Analysis")
  })

  it("waits for SSE authority after a permission update instead of applying the PATCH response", async () => {
    const patchResponse = snapshot("PATCH response")
    patchResponse.session.permission_mode = "full_access"
    mocks.updateAgentSession.mockResolvedValueOnce(patchResponse)

    const { result } = renderHook(() => useAgentSession("session-1"))
    const subscription = mocks.subscribeAgentEvents.mock.calls[0][0]
    act(() => {
      subscription.onEvent({ type: "snapshot", snapshot: snapshot() })
    })

    await act(async () => {
      await result.current.updatePermissionMode("full_access")
    })

    expect(mocks.updateAgentSession).toHaveBeenCalledWith("session-1", {
      permissionMode: "full_access",
    })
    expect(result.current.session?.permission_mode).toBe("ask_dangerous")

    const authoritative = snapshot("Authoritative")
    authoritative.session.permission_mode = "full_access"
    act(() => {
      subscription.onEvent({ type: "snapshot", snapshot: authoritative })
    })
    expect(result.current.session?.permission_mode).toBe("full_access")
  })

  it("ignores a stale snapshot refetch after the session changes", async () => {
    let resolveSnapshot!: (value: SessionSnapshot) => void
    mocks.getAgentSnapshot.mockReturnValueOnce(
      new Promise<SessionSnapshot>((resolve) => {
        resolveSnapshot = resolve
      }),
    )

    const { result, rerender } = renderHook(
      ({ sessionId }) => useAgentSession(sessionId),
      { initialProps: { sessionId: "session-1" } },
    )
    const firstSubscription = mocks.subscribeAgentEvents.mock.calls[0][0]
    act(() => {
      firstSubscription.onEvent({
        type: "snapshot",
        snapshot: streamingSnapshot(),
      })
      firstSubscription.onEvent({
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "part-1",
        part_type: "text",
        start_offset: 9,
        end_offset: 10,
        delta: "?",
      })
    })
    expect(mocks.getAgentSnapshot).toHaveBeenCalledWith("session-1")

    rerender({ sessionId: "session-2" })
    const secondSubscription = mocks.subscribeAgentEvents.mock.calls[1][0]
    act(() => {
      secondSubscription.onEvent({
        type: "snapshot",
        snapshot: snapshotFor("session-2", "Current"),
      })
      resolveSnapshot(snapshotFor("session-1", "Stale"))
    })

    await waitFor(() => expect(result.current.session?.id).toBe("session-2"))
    expect(result.current.session?.title).toBe("Current")
    expect(mocks.unsubscribe).toHaveBeenCalledOnce()
  })

  it("ignores a stale command error after the session changes", async () => {
    let rejectCommand!: (error: Error) => void
    mocks.dispatchAgentCommand.mockReturnValueOnce(
      new Promise<SessionSnapshot>((_resolve, reject) => {
        rejectCommand = reject
      }),
    )
    const parts: InputPart[] = [
      { type: "text", text: "Long-running command" },
    ]

    const { result, rerender } = renderHook(
      ({ sessionId }) => useAgentSession(sessionId),
      { initialProps: { sessionId: "session-1" } },
    )
    act(() => {
      mocks.subscribeAgentEvents.mock.calls[0][0].onEvent({
        type: "snapshot",
        snapshot: snapshotFor("session-1", "First"),
      })
    })
    let pendingCommand!: Promise<void>
    act(() => {
      pendingCommand = result.current.sendMessage(parts)
    })

    rerender({ sessionId: "session-2" })
    act(() => {
      mocks.subscribeAgentEvents.mock.calls[1][0].onEvent({
        type: "snapshot",
        snapshot: snapshotFor("session-2", "Current"),
      })
      rejectCommand(new Error("Stale failure"))
    })
    await act(async () => {
      await expect(pendingCommand).rejects.toThrow("Stale failure")
    })

    expect(result.current.session?.id).toBe("session-2")
    expect(result.current.session?.title).toBe("Current")
    expect(result.current.error).toBeNull()
  })

  it("unsubscribes and ignores stream callbacks after unmount", () => {
    const { unmount } = renderHook(() => useAgentSession("session-1"))
    const subscription = mocks.subscribeAgentEvents.mock.calls[0][0]

    unmount()
    act(() => {
      subscription.onEvent({
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "part-1",
        part_type: "text",
        start_offset: 1,
        end_offset: 2,
        delta: "x",
      })
    })

    expect(mocks.unsubscribe).toHaveBeenCalledOnce()
    expect(mocks.getAgentSnapshot).toHaveBeenCalledOnce()
  })
})
