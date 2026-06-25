import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createRemoteConnection,
  demoConnectionNodes,
  fetchRemoteConnections,
  remoteConnectionsApiPath,
  runRemoteConnectionCommand,
  testRemoteConnection,
  updateRemoteConnection,
  type RemoteConnectionStatus,
} from "@/lib/demo-connections"

import { apiRequest, buildWebSocketUrl } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
  buildWebSocketUrl: vi.fn(),
}))

const supportedStatuses: RemoteConnectionStatus[] = [
  "online",
  "offline",
  "error",
  "unknown",
]

describe("demo connection fallback data", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset()
    vi.mocked(buildWebSocketUrl).mockReset()
  })

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
        status_message: undefined,
      }),
    ])
  })

  it("creates and updates connections through the canonical backend endpoint", async () => {
    vi.mocked(apiRequest)
      .mockResolvedValueOnce({
        data: {
          id: "conn-new",
          name: "Live host",
          host: "login.example.org",
          port: 22,
          username: "alice",
          auth_method: "ssh_config",
          ssh_alias: "live",
          key_path: null,
          last_status: "unknown",
          last_error: null,
          skill_instructions: null,
        },
      })
      .mockResolvedValueOnce({
        data: {
          id: "conn-new",
          name: "Live host edited",
          host: "login.example.org",
          port: 2222,
          username: "alice",
          auth_method: "agent",
          ssh_alias: "live",
          key_path: null,
          last_status: "online",
          last_error: null,
          skill_instructions: "Use /data/live.",
        },
      })

    const created = await createRemoteConnection({
      name: "Live host",
      host: "login.example.org",
      port: 22,
      username: "alice",
      auth_method: "ssh_config",
      ssh_alias: "live",
      key_path: null,
      skill_instructions: null,
    })
    const updated = await updateRemoteConnection("conn-new", {
      name: "Live host edited",
      host: "login.example.org",
      port: 2222,
      username: "alice",
      auth_method: "agent",
      ssh_alias: "live",
      key_path: null,
      skill_instructions: "Use /data/live.",
    })

    expect(apiRequest).toHaveBeenNthCalledWith(1, "/connections", {
      method: "POST",
      body: JSON.stringify({
        name: "Live host",
        host: "login.example.org",
        port: 22,
        username: "alice",
        auth_method: "ssh_config",
        ssh_alias: "live",
        key_path: null,
        skill_instructions: null,
      }),
    })
    expect(apiRequest).toHaveBeenNthCalledWith(2, "/connections/conn-new", {
      method: "PATCH",
      body: JSON.stringify({
        name: "Live host edited",
        host: "login.example.org",
        port: 2222,
        username: "alice",
        auth_method: "agent",
        ssh_alias: "live",
        key_path: null,
        skill_instructions: "Use /data/live.",
      }),
    })
    expect(created.status).toBe("unknown")
    expect(updated).toEqual(expect.objectContaining({
      id: "conn-new",
      name: "Live host edited",
      status: "online",
      key_path: "",
      skill_instructions: "Use /data/live.",
    }))
  })

  it("tests a remote connection and normalizes the returned connection", async () => {
    vi.mocked(apiRequest).mockResolvedValueOnce({
      data: {
        status: "error",
        error: "Permission denied",
        checked_at: "2026-06-25T10:11:12Z",
        connection: {
          id: "conn-live",
          name: "Live host",
          host: "login.example.org",
          port: 22,
          username: "alice",
          auth_method: "ssh_config",
          ssh_alias: "live",
          key_path: null,
          last_status: "error",
          last_error: "Permission denied",
          last_checked_at: "2026-06-25T10:11:12Z",
          skill_instructions: null,
        },
      },
    })

    const result = await testRemoteConnection("conn-live")

    expect(apiRequest).toHaveBeenCalledWith("/connections/conn-live/test", {
      method: "POST",
    })
    expect(result).toEqual({
      status: "error",
      error: "Permission denied",
      checked_at: "2026-06-25T10:11:12Z",
      connection: expect.objectContaining({
        id: "conn-live",
        status: "error",
        status_message: "Permission denied",
        key_path: "",
      }),
    })
  })

  it("streams remote command frames over the connection websocket", async () => {
    vi.mocked(buildWebSocketUrl).mockReturnValue("ws://example.test/connections/conn-live/exec/ws")
    const frames: unknown[] = []

    class MockWebSocket {
      static OPEN = 1
      readyState = MockWebSocket.OPEN
      sent: string[] = []
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null

      constructor(readonly url: string) {
        frames.push({ url })
        queueMicrotask(() => this.onopen?.())
        queueMicrotask(() =>
          this.onmessage?.({ data: JSON.stringify({ type: "stdout", data: "ok\n" }) } as MessageEvent),
        )
        queueMicrotask(() =>
          this.onmessage?.({ data: JSON.stringify({ type: "exit", exit_code: 0 }) } as MessageEvent),
        )
      }

      send(data: string) {
        this.sent.push(data)
        frames.push({ sent: data })
      }

      close() {
        this.onclose?.()
      }
    }

    vi.stubGlobal("WebSocket", MockWebSocket)
    try {
      const result = await runRemoteConnectionCommand("conn-live", {
        command: "hostname",
        timeout_seconds: 5,
        onFrame: (frame) => frames.push(frame),
      })

      expect(buildWebSocketUrl).toHaveBeenCalledWith("/connections/conn-live/exec/ws")
      expect(frames).toContainEqual({
        sent: JSON.stringify({ command: "hostname", timeout_seconds: 5 }),
      })
      expect(result.frames).toEqual([
        { type: "stdout", data: "ok\n" },
        { type: "exit", exit_code: 0 },
      ])
      expect(result.exitCode).toBe(0)
      expect(result.output).toBe("ok\n")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("rejects when the remote command websocket closes before an exit frame", async () => {
    vi.mocked(buildWebSocketUrl).mockReturnValue("ws://example.test/connections/conn-live/exec/ws")

    class MockWebSocket {
      static OPEN = 1
      readyState = MockWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null

      constructor(readonly url: string) {
        queueMicrotask(() => this.onopen?.())
        queueMicrotask(() => this.onclose?.())
      }

      send() {}
      close() {
        this.onclose?.()
      }
    }

    vi.stubGlobal("WebSocket", MockWebSocket)
    try {
      await expect(
        runRemoteConnectionCommand("conn-live", {
          command: "hostname",
        }),
      ).rejects.toThrow("Remote command stream closed before completion")
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("rejects backend error frames from the remote command websocket", async () => {
    vi.mocked(buildWebSocketUrl).mockReturnValue("ws://example.test/connections/conn-live/exec/ws")
    const frames: unknown[] = []

    class MockWebSocket {
      static OPEN = 1
      readyState = MockWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null

      constructor(readonly url: string) {
        queueMicrotask(() => this.onopen?.())
        queueMicrotask(() =>
          this.onmessage?.({
            data: JSON.stringify({ type: "error", message: "Unauthorized" }),
          } as MessageEvent),
        )
      }

      send() {}
      close() {
        this.onclose?.()
      }
    }

    vi.stubGlobal("WebSocket", MockWebSocket)
    try {
      await expect(
        runRemoteConnectionCommand("conn-live", {
          command: "hostname",
          onFrame: (frame) => frames.push(frame),
        }),
      ).rejects.toThrow("Unauthorized")
      expect(frames).toEqual([{ type: "error", message: "Unauthorized" }])
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
