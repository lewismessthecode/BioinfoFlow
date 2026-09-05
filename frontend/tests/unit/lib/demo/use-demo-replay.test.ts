import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useDemoReplay } from "@/lib/demo/use-demo-replay"
import type {
  AgentEvent,
  RunView,
  SessionSnapshot,
} from "@/lib/agent/contracts"
import type { DemoTimelineItem } from "@/lib/demo/types"

const sessionSnapshot: SessionSnapshot = {
  session: {
    id: "session-1",
    user_id: "demo-user",
    workspace_id: "workspace-demo",
    project_id: "project-demo",
    title: "Demo",
    model: {
      provider: "demo",
      model: "demo-model",
      display_name: "Demo Model",
      supports_vision: true,
      supports_reasoning: true,
      supports_tools: true,
    },
    permission_mode: "ask_dangerous",
    workspace_access: "read_write",
    status: "active",
    created_at: "2026-04-24T09:00:00Z",
    updated_at: "2026-04-24T09:00:00Z",
  },
  runs: [],
  entries: [],
  active_run: null,
}

const runningRun: RunView = {
  id: "run-1",
  session_id: "session-1",
  status: "running",
  phase: "model",
  revision: 1,
  started_at: "2026-04-24T09:00:01Z",
  completed_at: null,
  termination_reason: null,
  error: null,
  created_at: "2026-04-24T09:00:01Z",
  updated_at: "2026-04-24T09:00:01Z",
}

describe("useDemoReplay", () => {
  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it("applies the formal Agent store events for the injected workbench state", async () => {
    vi.useFakeTimers()
    const events: AgentEvent[] = [
      { type: "snapshot", snapshot: sessionSnapshot },
      { type: "run.updated", run: runningRun },
      {
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "reasoning-1",
        part_type: "reasoning_summary",
        start_offset: 0,
        end_offset: 26,
        delta: "I will inspect the inputs.",
      },
      {
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "text-1",
        part_type: "text",
        start_offset: 0,
        end_offset: 22,
        delta: "Starting the workflow.",
      },
      {
        type: "tool.updated",
        run_id: "run-1",
        tool: {
          call_id: "call-1",
          group_id: "group-1",
          execution_mode: "serial",
          name: "runs.submit",
          display_name: "Run workflow",
          category: "workflow",
          summary: "Run the RNA-seq workflow",
          arguments: { workflow: "rnaseq-quant-mini" },
          status: "completed",
          revision: 1,
          started_at: "2026-04-24T09:00:02Z",
          completed_at: "2026-04-24T09:00:03Z",
          input_summary: null,
          output_summary: "Run submitted",
          error: null,
        },
      },
      {
        type: "entry.committed",
        entry: {
          id: "assistant-1",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 2,
          created_at: "2026-04-24T09:00:04Z",
          type: "message",
          payload: {
            role: "assistant",
            parts: [
              { id: "reasoning", type: "reasoning_summary", text: "I will inspect the inputs." },
              { id: "text", type: "text", text: "Starting the workflow." },
              {
                id: "call",
                type: "tool_call",
                call_id: "call-1",
                group_id: "group-1",
                execution_mode: "serial",
                name: "runs.submit",
                display_name: "Run workflow",
                category: "workflow",
                summary: "Run the RNA-seq workflow",
                arguments: { workflow: "rnaseq-quant-mini" },
              },
            ],
          },
        },
      },
      {
        type: "run.updated",
        run: {
          ...runningRun,
          status: "completed",
          phase: null,
          revision: 2,
          completed_at: "2026-04-24T09:00:05Z",
          termination_reason: "completed",
          updated_at: "2026-04-24T09:00:05Z",
        },
      },
    ]
    const timeline: DemoTimelineItem[] = events.map((event, index) => ({
      t: index * 10,
      kind: "agent",
      event,
    }))
    const recording = timeline.map((item) => JSON.stringify(item)).join("\n")

    const { result } = renderHook(() => useDemoReplay(recording, false))

    expect(result.current.sessionState.view?.conversation.id).toBe(
      sessionSnapshot.session.id,
    )
    act(() => result.current.play())
    await act(async () => vi.runAllTimersAsync())

    expect(result.current.status).toBe("finished")
    expect(result.current.sessionState.view?.activeWork).toBeNull()
    expect(result.current.sessionState.view?.runs[0]).toMatchObject({
      status: "completed",
      completedAt: "2026-04-24T09:00:05Z",
    })
    expect(result.current.sessionState.view?.transcript).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "message", text: "Starting the workflow." }),
        expect.objectContaining({ type: "activity_group" }),
      ]),
    )
  })

  it("does not autoplay when the user prefers reduced motion", async () => {
    vi.useFakeTimers()
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: true,
        media: "(prefers-reduced-motion: reduce)",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }),
    })
    const recording = JSON.stringify({
      t: 0,
      kind: "agent",
      event: { type: "snapshot", snapshot: sessionSnapshot },
    })
    const { result } = renderHook(() => useDemoReplay(recording, true))

    await act(async () => vi.runAllTimersAsync())

    expect(result.current.status).toBe("idle")
  })
})
