import { describe, expect, it } from "vitest"

import {
  demoConnectionNodes,
  type RemoteConnectionStatus,
} from "@/lib/demo-connections"

const supportedStatuses: RemoteConnectionStatus[] = [
  "online",
  "offline",
  "partial",
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
})
