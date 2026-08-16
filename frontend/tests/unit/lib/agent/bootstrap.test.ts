import { beforeEach, describe, expect, it, vi } from "vitest"

import { getAgentUiBootstrap } from "@/lib/agent/bootstrap"
import { apiRequest } from "@/lib/api"

vi.mock("@/lib/api", () => ({ apiRequest: vi.fn() }))

const mockedApiRequest = vi.mocked(apiRequest)

describe("getAgentUiBootstrap", () => {
  beforeEach(() => mockedApiRequest.mockReset())

  it("normalizes the versioned bootstrap and keeps stable selector slots", async () => {
    mockedApiRequest.mockResolvedValueOnce({
      data: {
        protocol_version: 1,
        capabilities: {
          reasoning: true,
          tool_activity: true,
          approvals: true,
          artifacts: true,
          starter_prompts: true,
          multi_target_execution: true,
          retry: true,
          edit_and_resend: true,
        },
        execution_scope: { mode: "manual", target_ids: ["remote-1"] },
        execution_targets: [
          {
            id: "remote-1",
            handle: "ssh:cluster-a",
            alias: "Cluster A",
            kind: "remote_ssh",
            status: "online",
            primary: true,
          },
        ],
        starter_prompts: [
          {
            id: "review-run",
            title: "Review the latest run",
            prompt: "Review the latest run and explain failures.",
            icon: "review",
          },
        ],
        composer_hint: "Add context or choose a skill",
      },
    })

    await expect(getAgentUiBootstrap("project-1", "en")).resolves.toEqual(
      expect.objectContaining({
        protocolVersion: 1,
        executionScope: { mode: "manual", targetIds: ["remote-1"] },
        executionTargets: [
          expect.objectContaining({ alias: "Cluster A", handle: "ssh:cluster-a" }),
        ],
        starterPrompts: [
          expect.objectContaining({ id: "review-run", icon: "review" }),
        ],
      }),
    )
    expect(mockedApiRequest).toHaveBeenCalledWith("/agent/ui/bootstrap", {
      params: { project_id: "project-1", locale: "en" },
    })
  })

  it("falls back locally when the payload is incompatible or unsafe", async () => {
    mockedApiRequest.mockResolvedValueOnce({
      data: {
        protocol_version: 2,
        starter_prompts: [
          { id: "bad", title: "", prompt: "x".repeat(3000), icon: "unknown" },
        ],
      },
    })

    const bootstrap = await getAgentUiBootstrap(null, "zh-CN")

    expect(bootstrap.degradedReason).toBe("unsupported_version")
    expect(bootstrap.executionTargets).toEqual([
      expect.objectContaining({ id: "local", alias: "本地" }),
    ])
    expect(bootstrap.starterPrompts).toHaveLength(3)
    expect(bootstrap.starterPrompts[0].prompt).toContain("工作区")
  })
})
