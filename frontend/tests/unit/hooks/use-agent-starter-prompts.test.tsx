import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({ getAgentStarterPrompts: vi.fn() }))

vi.mock("@/lib/agent/starter-prompts", () => ({
  getAgentStarterPrompts: mocks.getAgentStarterPrompts,
}))

import { useAgentStarterPrompts } from "@/hooks/use-agent-starter-prompts"

describe("useAgentStarterPrompts", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mocks.getAgentStarterPrompts.mockReset()
  })

  afterEach(() => vi.useRealTimers())

  it("shows fallback immediately and refreshes generated prompts in the background", async () => {
    mocks.getAgentStarterPrompts
      .mockResolvedValueOnce({
        prompts: ["Review the project"],
        source: "fallback",
        refresh_pending: true,
      })
      .mockResolvedValueOnce({
        prompts: ["Inspect workflow inputs", "Review recent runs"],
        source: "cache",
        refresh_pending: false,
      })

    const { result } = renderHook(() =>
      useAgentStarterPrompts("project-1", "en", { pollIntervalMs: 10 }),
    )

    await act(async () => {})
    expect(result.current.prompts).toEqual(["Review the project"])
    expect(result.current.isLoading).toBe(false)
    expect(result.current.refreshPending).toBe(true)

    await act(async () => vi.advanceTimersByTimeAsync(10))

    expect(result.current.prompts).toEqual([
      "Inspect workflow inputs",
      "Review recent runs",
    ])
    expect(result.current.refreshPending).toBe(false)
    expect(mocks.getAgentStarterPrompts).toHaveBeenNthCalledWith(1, {
      projectId: "project-1",
      locale: "en",
      signal: expect.any(AbortSignal),
    })
    expect(mocks.getAgentStarterPrompts).toHaveBeenCalledTimes(2)
  })

  it("does not request prompts without a project", async () => {
    const { result } = renderHook(() =>
      useAgentStarterPrompts(null, "en", { pollIntervalMs: 10 }),
    )

    await act(async () => {})

    expect(result.current.prompts).toEqual([])
    expect(result.current.isLoading).toBe(false)
    expect(mocks.getAgentStarterPrompts).not.toHaveBeenCalled()
  })
})
