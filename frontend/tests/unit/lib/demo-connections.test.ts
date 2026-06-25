import { describe, expect, it, vi } from "vitest"

import {
  demoConnectionNodes,
  fetchRemoteConnections,
  remoteConnectionsApiPath,
  type RemoteConnectionStatus,
} from "@/lib/demo-connections"

import { apiRequest } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}))

const supportedStatuses: RemoteConnectionStatus[] = [
  "online",
  "offline",
  "error",
  "unknown",
]

describe("demo connection fallback data", () => {
  it("matches the planned backend connection object shape", () => {
    expect(demoConnectionNodes.length).toBeGreaterThan(0)

    for (const connection of demoConnectionNodes) {
      expect(connection).toEqual(
        expect.objectContaining({
          id: expect.any(String),
          name: expect.any(String),
          host: expect.any(String),
          port: expect.any(Number),
          username: expect.any(String),
          auth_method: expect.any(String),
          ssh_alias: expect.any(String),
          key_path: expect.any(String),
          status: expect.any(String),
          skill_instructions: expect.any(String),
        }),
      )
      expect(supportedStatuses).toContain(connection.status)
      expect(connection).not.toHaveProperty("tags")
      expect(connection).not.toHaveProperty("paths")
      expect(connection).not.toHaveProperty("apis")
      expect(connection).not.toHaveProperty("environmentVariables")
      expect(connection).not.toHaveProperty("startupSnippet")
    }
  })

  it("fetches live connections from the canonical backend endpoint", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({
      data: [
        {
          id: "conn-live",
          name: "Live host",
          host: "login.example.org",
          port: 22,
          username: "alice",
          auth_method: "ssh_config",
          ssh_alias: null,
          key_path: null,
          last_status: "online",
          last_error: null,
          skill_instructions: "Use module load nextflow.",
        },
      ],
    })

    const connections = await fetchRemoteConnections()

    expect(apiRequest).toHaveBeenCalledWith("/connections")
    expect(remoteConnectionsApiPath).toBe("/connections")
    expect(connections).toEqual([
      expect.objectContaining({
        id: "conn-live",
        status: "online",
        ssh_alias: "",
        key_path: "",
      }),
    ])
  })
})
