import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiRequest } from "@/lib/api"
import { getAgentStarterPrompts } from "@/lib/agent/starter-prompts"

vi.mock("@/lib/api", () => ({ apiRequest: vi.fn() }))

const mockedApiRequest = vi.mocked(apiRequest)

describe("starter prompt client", () => {
  beforeEach(() => mockedApiRequest.mockReset())

  it("loads project-aware prompts through the authenticated Agent API", async () => {
    const controller = new AbortController()
    const response = {
      prompts: ["Inspect workflow inputs", "Review recent runs"],
      source: "cache" as const,
      refresh_pending: false,
    }
    mockedApiRequest.mockResolvedValueOnce({ data: response })

    await expect(
      getAgentStarterPrompts({
        projectId: "project-1",
        locale: "zh-CN",
        signal: controller.signal,
      }),
    ).resolves.toEqual(response)

    expect(mockedApiRequest).toHaveBeenCalledWith("/agent/starter-prompts", {
      params: { project_id: "project-1", locale: "zh-CN" },
      signal: controller.signal,
    })
  })
})
