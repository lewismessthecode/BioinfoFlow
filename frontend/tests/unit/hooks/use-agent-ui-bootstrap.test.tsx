import { renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useAgentUiBootstrap } from "@/hooks/use-agent-ui-bootstrap"
import { getAgentUiBootstrap } from "@/lib/agent/bootstrap"

vi.mock("@/lib/agent/bootstrap", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("@/lib/agent/bootstrap")>()
  return { ...original, getAgentUiBootstrap: vi.fn() }
})

vi.mock("next-intl", () => ({ useLocale: () => "en" }))

const mockedGetBootstrap = vi.mocked(getAgentUiBootstrap)

describe("useAgentUiBootstrap", () => {
  beforeEach(() => mockedGetBootstrap.mockReset())

  it("loads bootstrap for the current project and ignores stale responses", async () => {
    let resolveFirst!: (value: Awaited<ReturnType<typeof getAgentUiBootstrap>>) => void
    mockedGetBootstrap
      .mockReturnValueOnce(new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce(bootstrap("second"))
    const view = renderHook(
      ({ projectId }) => useAgentUiBootstrap(projectId),
      { initialProps: { projectId: "project-1" } },
    )

    view.rerender({ projectId: "project-2" })
    await waitFor(() => expect(view.result.current.bootstrap?.composerHint).toBe("second"))
    resolveFirst(bootstrap("stale"))

    await waitFor(() => expect(view.result.current.bootstrap?.composerHint).toBe("second"))
    expect(mockedGetBootstrap).toHaveBeenNthCalledWith(2, "project-2", "en")
  })
})

function bootstrap(composerHint: string) {
  return {
    protocolVersion: 1 as const,
    capabilities: {
      reasoning: true,
      toolActivity: true,
      approvals: true,
      artifacts: true,
      starterPrompts: true,
      multiTargetExecution: false,
      retry: true,
      editAndResend: true,
    },
    model: null,
    permissionMode: "ask_dangerous" as const,
    executionTargets: [],
    executionScope: { mode: "auto" as const, targetIds: [] },
    starterPrompts: [],
    composerHint,
    degradedReason: null,
  }
}
