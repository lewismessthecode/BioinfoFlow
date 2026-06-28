import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ConnectionsPage from "@/app/(app)/connections/page"
import { apiRequest, buildWebSocketUrl } from "@/lib/api"
import type { RemoteConnection } from "@/lib/demo-connections"
import enMessages from "@/messages/en.json"

function readMessage(namespace: string, key: string, params?: Record<string, string | number>) {
  const path = `${namespace}.${key}`.split(".")
  let value: unknown = enMessages

  for (const part of path) {
    value = typeof value === "object" && value !== null ? (value as Record<string, unknown>)[part] : undefined
  }

  if (typeof value !== "string") {
    return key
  }

  return Object.entries(params ?? {}).reduce(
    (text, [name, replacement]) => text.replaceAll(`{${name}}`, String(replacement)),
    value,
  )
}

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations:
    (namespace: string) =>
    (key: string, params?: Record<string, string | number>) =>
      readMessage(namespace, key, params),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
  buildWebSocketUrl: vi.fn(),
  getApiErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
}))

const apiRequestMock = vi.mocked(apiRequest)
const buildWebSocketUrlMock = vi.mocked(buildWebSocketUrl)

const liveConnection: RemoteConnection = {
  id: "live-connection-1",
  name: "Live HPC",
  host: "login.live.example.org",
  port: 2222,
  username: "bioflow",
  auth_method: "ssh_config",
  ssh_alias: "live-hpc",
  key_path: "",
  status: "unknown",
  skill_instructions: "Use /data/live for analysis outputs.",
}

const secondConnection: RemoteConnection = {
  id: "live-connection-2",
  name: "Backup HPC",
  host: "backup.live.example.org",
  port: 22,
  username: "bioflow",
  auth_method: "agent",
  ssh_alias: "",
  key_path: "",
  status: "unknown",
  skill_instructions: "Use /backup/live for read-only checks.",
}

describe("ConnectionsPage", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    buildWebSocketUrlMock.mockReset()
    vi.clearAllMocks()
    apiRequestMock.mockRejectedValue(new Error("backend unavailable"))
    buildWebSocketUrlMock.mockImplementation((path: string) => `ws://example.test${path}`)
  })

  it("focuses the main flow on SSH config and Agent context", async () => {
    const user = userEvent.setup()

    render(<ConnectionsPage />)

    expect(screen.getByRole("heading", { name: "SSH connections" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    expect(screen.getByLabelText("SSH alias")).toBeInTheDocument()
    expect(screen.queryByLabelText("Private key path")).not.toBeInTheDocument()
    expect(screen.getAllByText("Agent instructions")[0]).toBeInTheDocument()
    expect(screen.getByText("Import instructions file")).toBeInTheDocument()

    expect(screen.queryByText("Tags")).not.toBeInTheDocument()
    expect(screen.queryByText("Accessible paths")).not.toBeInTheDocument()
    expect(screen.queryByText("APIs and ports")).not.toBeInTheDocument()
    expect(screen.queryByText("Environment variables")).not.toBeInTheDocument()
    expect(screen.queryByText("Startup snippet")).not.toBeInTheDocument()
  })

  it("shows an empty state when the backend returns no live connections", async () => {
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    expect(
      await screen.findByText("No connections yet. Add an SSH environment to get started."),
    ).toBeInTheDocument()
    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
  })

  it("does not show demo connections when the live backend is unavailable", async () => {
    render(<ConnectionsPage />)

    expect(await screen.findByText("Could not load SSH connections. Check the service and try again.")).toBeInTheDocument()
    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Quick check" })).not.toBeInTheDocument()
  })

  it("saves new connections through the backend", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    apiRequestMock.mockResolvedValueOnce({ data: liveConnection })

    render(<ConnectionsPage />)

    await user.click(screen.getByRole("button", { name: "Add connection" }))
    await user.type(screen.getByLabelText("Connection name"), "Live HPC")
    await user.type(screen.getByLabelText("Host or IP"), "login.live.example.org")
    await user.clear(screen.getByLabelText("Port"))
    await user.type(screen.getByLabelText("Port"), "2222")
    await user.type(screen.getByLabelText("Username"), "bioflow")
    await user.type(screen.getByLabelText("SSH alias"), "live-hpc")
    await user.type(
      screen.getByLabelText("Agent instructions"),
      "Use /data/live for analysis outputs.",
    )
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Live HPC",
          host: "login.live.example.org",
          port: 2222,
          username: "bioflow",
          auth_method: "ssh_config",
          ssh_alias: "live-hpc",
          key_path: null,
          skill_instructions: "Use /data/live for analysis outputs.",
        }),
      }),
    )
    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
  })

  it("keeps invalid ports on the client instead of silently replacing them", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    await user.click(screen.getByRole("button", { name: "Add connection" }))
    await user.type(screen.getByLabelText("Host or IP"), "login.live.example.org")
    await user.clear(screen.getByLabelText("Port"))
    await user.type(screen.getByLabelText("Port"), "70000")
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    expect(await screen.findByText("Port must be between 1 and 65535.")).toBeInTheDocument()
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("requires an SSH alias before saving SSH config connections", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    await user.click(screen.getByRole("button", { name: "Add connection" }))
    await user.type(screen.getByLabelText("Host or IP"), "login.live.example.org")
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    const error = await screen.findByRole("alert")
    expect(error).toHaveTextContent("Enter an SSH alias.")
    expect(screen.getByLabelText("SSH alias")).toHaveAttribute("aria-invalid", "true")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("tests the selected SSH connection and refreshes the visible status", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        status: "online",
        error: null,
        checked_at: "2026-06-25T10:11:12Z",
        connection: {
          ...liveConnection,
          last_status: "online",
          last_error: null,
          last_checked_at: "2026-06-25T10:11:12Z",
        },
      },
    })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Test connection" }))

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections/live-connection-1/test", {
        method: "POST",
      }),
    )
    expect(await screen.findAllByText("Online")).not.toHaveLength(0)
  })

  it("does not switch the selected connection when a stale test finishes", async () => {
    const user = userEvent.setup()
    let resolveTest: (value: unknown) => void = () => {}
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, secondConnection] })
    apiRequestMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveTest = resolve
        }),
    )

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Test connection" }))
    await user.click(screen.getByRole("button", { name: /Backup HPC/ }))

    resolveTest({
      data: {
        status: "online",
        error: null,
        checked_at: "2026-06-25T10:11:12Z",
        connection: {
          ...liveConnection,
          last_status: "online",
          last_error: null,
          last_checked_at: "2026-06-25T10:11:12Z",
        },
      },
    })

    await waitFor(() => expect(screen.getByRole("heading", { name: "Backup HPC" })).toBeInTheDocument())
    expect(screen.queryByRole("heading", { name: "Live HPC" })).not.toBeInTheDocument()
  })

  it("opens an existing connection for editing and saves the patch", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...liveConnection,
        name: "Live HPC Login",
        host: "login2.live.example.org",
        last_status: "unknown",
      },
    })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Edit connection" }))
    expect(screen.getByRole("heading", { name: "Edit SSH connection" })).toBeInTheDocument()

    await user.clear(screen.getByLabelText("Connection name"))
    await user.type(screen.getByLabelText("Connection name"), "Live HPC Login")
    await user.clear(screen.getByLabelText("Host or IP"))
    await user.type(screen.getByLabelText("Host or IP"), "login2.live.example.org")
    await user.click(screen.getByRole("button", { name: "Save changes" }))

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections/live-connection-1", {
        method: "PATCH",
        body: JSON.stringify({
          name: "Live HPC Login",
          host: "login2.live.example.org",
          port: 2222,
          username: "bioflow",
          auth_method: "ssh_config",
          ssh_alias: "live-hpc",
          key_path: null,
          skill_instructions: "Use /data/live for analysis outputs.",
        }),
      }),
    )
    expect(await screen.findByRole("heading", { name: "Live HPC Login" })).toBeInTheDocument()
  })

  it("requires a private key path for key file connections", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    await user.click(screen.getByRole("button", { name: "Add connection" }))
    await user.type(screen.getByLabelText("Host or IP"), "login.live.example.org")
    await user.click(screen.getByRole("button", { name: /Private key/ }))
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    expect(await screen.findByText("Enter a private key path.")).toBeInTheDocument()
    expect(screen.getByLabelText("Private key path")).toHaveAttribute("aria-invalid", "true")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("does not send an SSH alias for key file connections", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...liveConnection,
        auth_method: "key_file",
        ssh_alias: null,
        key_path: "~/.ssh/id_ed25519",
      },
    })

    render(<ConnectionsPage />)

    await user.click(screen.getByRole("button", { name: "Add connection" }))
    await user.type(screen.getByLabelText("Connection name"), "Key HPC")
    await user.type(screen.getByLabelText("Host or IP"), "login.key.example.org")
    await user.type(screen.getByLabelText("Username"), "bioflow")
    await user.click(screen.getByRole("button", { name: /Private key/ }))
    await user.type(screen.getByLabelText("Private key path"), "~/.ssh/id_ed25519")
    expect(screen.queryByLabelText("SSH alias")).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Key HPC",
          host: "login.key.example.org",
          port: 22,
          username: "bioflow",
          auth_method: "key_file",
          ssh_alias: null,
          key_path: "~/.ssh/id_ed25519",
          skill_instructions: null,
        }),
      }),
    )
  })

  it("adds preset and dropped Agent instructions", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    await user.click(screen.getByRole("button", { name: "Add connection" }))
    await user.click(screen.getByRole("button", { name: "Insert preset" }))
    await user.click(await screen.findByRole("menuitem", { name: "Nextflow HPC" }))
    expect(screen.getByLabelText("Agent instructions")).toHaveValue(
      "Load the site environment before diagnostics.\nRun module load nextflow when modules are available.\nCheck workflow outputs, .nextflow.log, and task directories under work/ before reruns.",
    )

    const file = new File(["Outputs live under /scratch/project/results."], "skill.txt", {
      type: "text/plain",
    })
    Object.defineProperty(file, "text", {
      value: vi.fn().mockResolvedValue("Outputs live under /scratch/project/results."),
    })
    fireEvent.drop(screen.getByText("Import instructions file"), {
      dataTransfer: { files: [file] },
    })

    expect(await screen.findByDisplayValue(/scratch\/project\/results/)).toBeInTheDocument()
  })

  it("streams a remote probe command back into the detail panel", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    class MockWebSocket {
      static OPEN = 1
      readyState = MockWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null

      constructor(readonly url: string) {
        queueMicrotask(() => this.onopen?.())
        queueMicrotask(() =>
          this.onmessage?.({ data: JSON.stringify({ type: "stdout", data: "bioinfoflow-ok\n" }) } as MessageEvent),
        )
        queueMicrotask(() =>
          this.onmessage?.({ data: JSON.stringify({ type: "exit", exit_code: 0 }) } as MessageEvent),
        )
      }

      send() {}
      close() {
        this.onclose?.()
      }
    }

    vi.stubGlobal("WebSocket", MockWebSocket)
    try {
      render(<ConnectionsPage />)

      expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
      await user.click(screen.getByRole("button", { name: "Quick check" }))

      expect(await screen.findByText("bioinfoflow-ok")).toBeInTheDocument()
      expect(buildWebSocketUrlMock).toHaveBeenCalledWith("/connections/live-connection-1/exec/ws")
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
