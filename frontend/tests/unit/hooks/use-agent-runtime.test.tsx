import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import type { AgentRuntimeEvent, AgentRuntimeSession } from "@/lib/agent-runtime"

const mocks = vi.hoisted(() => ({
  subscribeAgentRuntimeEvents: vi.fn(),
  getAgentRuntimeState: vi.fn(),
  listAgentRuntimeSessions: vi.fn(),
}))

vi.mock("@/lib/runtime", () => ({
  getCurrentRuntime: () => ({ mode: "live" }),
}))

vi.mock("@/lib/agent-runtime", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/agent-runtime")>()
  return {
    ...actual,
    createAgentRuntimeSession: vi.fn(),
    createAgentRuntimeTurn: vi.fn(),
    decideAgentRuntimeAction: vi.fn(),
    getAgentRuntimeState: mocks.getAgentRuntimeState,
    interruptAgentRuntimeTurn: vi.fn(),
    listAgentRuntimeSessions: mocks.listAgentRuntimeSessions,
    subscribeAgentRuntimeEvents: mocks.subscribeAgentRuntimeEvents,
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

describe("useAgentRuntime", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.listAgentRuntimeSessions.mockResolvedValue([session])
    mocks.getAgentRuntimeState.mockResolvedValue({ session, turns: [], events: [] })
    mocks.subscribeAgentRuntimeEvents.mockReturnValue(vi.fn())
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
})
