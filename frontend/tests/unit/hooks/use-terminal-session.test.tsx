import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { TerminalSession } from "@/lib/types"

const {
  apiRequestMock,
  buildWebSocketUrlMock,
  getApiErrorMessageMock,
} = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
  buildWebSocketUrlMock: vi.fn(),
  getApiErrorMessageMock: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  buildWebSocketUrl: (...args: unknown[]) => buildWebSocketUrlMock(...args),
  getApiErrorMessage: (...args: unknown[]) => getApiErrorMessageMock(...args),
}))

import { useTerminalSession } from "@/hooks/use-terminal-session"

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: MockWebSocket[] = []

  readonly url: string
  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  emit(type: "ready" | "cwd" | "exit" | "error", payload: Record<string, unknown>) {
    this.onmessage?.({
      data: JSON.stringify({ type, ...payload }),
    } as MessageEvent)
  }

  emitRaw(data: string) {
    this.onmessage?.({ data } as MessageEvent)
  }
}

describe("useTerminalSession", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    buildWebSocketUrlMock.mockReset()
    getApiErrorMessageMock.mockReset()
    MockWebSocket.instances = []
    vi.stubGlobal("WebSocket", MockWebSocket)
    buildWebSocketUrlMock.mockImplementation((path: string) => `ws://example.test${path}`)
    getApiErrorMessageMock.mockReturnValue("Failed to start terminal")
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("stays idle and does not start a session when disabled", () => {
    const { result } = renderHook(() =>
      useTerminalSession({ projectId: "project-1", enabled: false })
    )

    expect(result.current.connectionState).toBe("idle")
    expect(result.current.session).toBeNull()
    expect(apiRequestMock).not.toHaveBeenCalled()
  })

  it("creates a terminal session, reacts to websocket messages, and reconnects", async () => {
    const initialSession: TerminalSession = {
      id: "session-1",
      project_id: "project-1",
      shell: "/bin/zsh",
      cwd: "/workspace",
      status: "starting",
      target_type: "local",
      target_label: "local",
      remote_connection_id: null,
    }
    const onMessage = vi.fn()
    apiRequestMock.mockResolvedValue({ data: initialSession })

    const { result } = renderHook(() =>
      useTerminalSession({ projectId: "project-1", enabled: true, onMessage })
    )

    await waitFor(() => expect(result.current.session?.id).toBe("session-1"))
    expect(result.current.connectionState).toBe("connecting")
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(buildWebSocketUrlMock).toHaveBeenCalledWith(
      "/terminal/sessions/session-1/ws"
    )

    const socket = MockWebSocket.instances[0]
    act(() => {
      socket.readyState = MockWebSocket.OPEN
      socket.onopen?.()
    })

    expect(result.current.connectionState).toBe("connecting")
    expect(result.current.sendInput("before-ready")).toBe(false)
    expect(socket.sent).toEqual([])

    act(() => {
      socket.emit("ready", {
        session: { ...initialSession, status: "ready" },
      })
      socket.emit("cwd", { cwd: "/workspace/results" })
    })

    await waitFor(() => expect(result.current.connectionState).toBe("connected"))
    expect(result.current.session?.cwd).toBe("/workspace/results")
    expect(onMessage).toHaveBeenCalledTimes(2)

    act(() => {
      expect(result.current.sendInput("pwd")).toBe(true)
      expect(result.current.resize(120, 40)).toBe(true)
      expect(result.current.chdir("logs")).toBe(true)
    })

    expect(socket.sent).toEqual([
      JSON.stringify({ type: "input", data: "pwd" }),
      JSON.stringify({ type: "resize", cols: 120, rows: 40 }),
      JSON.stringify({ type: "chdir", path: "logs" }),
    ])

    act(() => {
      socket.emit("exit", { exit_code: 0 })
    })
    expect(result.current.connectionState).toBe("exited")

    act(() => {
      result.current.reconnect()
    })

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(2))
    expect(apiRequestMock).toHaveBeenCalledTimes(2)
  })

  it("clears websocket readiness after malformed terminal messages", async () => {
    const initialSession: TerminalSession = {
      id: "session-1",
      project_id: "project-1",
      shell: "/bin/zsh",
      cwd: "/workspace",
      status: "starting",
      target_type: "local",
      target_label: "local",
      remote_connection_id: null,
    }
    apiRequestMock.mockResolvedValue({ data: initialSession })

    const { result } = renderHook(() =>
      useTerminalSession({ projectId: "project-1", enabled: true })
    )

    await waitFor(() => expect(MockWebSocket.instances).toHaveLength(1))
    const socket = MockWebSocket.instances[0]

    act(() => {
      socket.readyState = MockWebSocket.OPEN
      socket.emit("ready", {
        session: { ...initialSession, status: "ready" },
      })
    })

    await waitFor(() => expect(result.current.connectionState).toBe("connected"))
    expect(result.current.sendInput("before-error")).toBe(true)

    act(() => {
      socket.emitRaw("{not-json")
    })

    expect(result.current.connectionState).toBe("error")
    expect(result.current.error).toBe("Failed to parse terminal event")
    expect(result.current.sendInput("after-error")).toBe(false)
  })
})
