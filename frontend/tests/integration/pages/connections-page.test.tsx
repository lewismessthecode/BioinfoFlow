import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { toast } from "sonner"

import ConnectionsPage from "@/app/(app)/connections/page"
import { ApiError, apiRequest, buildWebSocketUrl } from "@/lib/api"
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

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status?: number

    constructor(message: string, options?: { status?: number }) {
      super(message)
      this.name = "ApiError"
      this.status = options?.status
    }
  }

  return {
    ApiError,
    apiRequest: vi.fn(),
    buildWebSocketUrl: vi.fn(),
    getApiErrorMessage: (error: unknown, fallback: string) =>
      error instanceof Error ? error.message : fallback,
  }
})

const apiRequestMock = vi.mocked(apiRequest)
const buildWebSocketUrlMock = vi.mocked(buildWebSocketUrl)
const toastSuccessMock = vi.mocked(toast.success)
const toastErrorMock = vi.mocked(toast.error)

type TestUser = ReturnType<typeof userEvent.setup>

async function openAddConnectionPanel(user: TestUser) {
  await user.click(screen.getByRole("button", { name: "Add connection" }))
  return screen.getByRole("complementary", { name: "Host configuration" })
}

function getConnectionPanel() {
  return screen.getByRole("complementary", { name: "Host configuration" })
}

async function clickPanelButton(user: TestUser, name: string | RegExp) {
  await user.click(within(getConnectionPanel()).getByRole("button", { name }))
}

async function openAdvancedSsh(user: TestUser) {
  await user.click(within(getConnectionPanel()).getByText("Advanced SSH settings"))
}

async function openEditConnectionPanel(user: TestUser, connectionName = "Live HPC") {
  await user.click(screen.getByRole("button", { name: `Edit connection: ${connectionName}` }))
  return getConnectionPanel()
}

async function clickConnectionAction(user: TestUser, name: string | RegExp) {
  await user.click(within(getConnectionPanel()).getByRole("button", { name: "Actions" }))
  await user.click(await screen.findByRole("menuitem", { name }))
}

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

const passwordConnection: RemoteConnection = {
  id: "live-connection-password",
  name: "Password HPC",
  host: "password.live.example.org",
  port: 22,
  username: "bioflow",
  auth_method: "password",
  ssh_alias: "",
  key_path: "",
  status: "unknown",
  skill_instructions: "Use /password/live for checks.",
}

describe("ConnectionsPage", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    buildWebSocketUrlMock.mockReset()
    vi.clearAllMocks()
    apiRequestMock.mockRejectedValue(new Error("backend unavailable"))
    buildWebSocketUrlMock.mockImplementation((path: string) => `ws://example.test${path}`)
  })

  it("opens a single-entry Termius-style host panel", async () => {
    const user = userEvent.setup()

    render(<ConnectionsPage />)

    expect(screen.getByRole("heading", { name: "SSH hosts" })).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Add connection" })).toHaveLength(1)
    expect(screen.queryByText(/quick open/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Runtime boundary/i)).not.toBeInTheDocument()

    const panel = await openAddConnectionPanel(user)
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(within(panel).getByRole("heading", { name: "New host" })).toBeInTheDocument()
    expect(within(panel).getByLabelText("Address")).toBeInTheDocument()
    expect(within(panel).getByLabelText("Label")).toBeInTheDocument()
    expect(within(panel).getByLabelText("SSH on port")).toBeInTheDocument()
    expect(within(panel).getByLabelText("Username")).toBeInTheDocument()
    expect(within(panel).getByText("Credentials")).toBeInTheDocument()
    expect(within(panel).getByLabelText("Host Skill")).toBeInTheDocument()
    expect(within(panel).getByRole("button", { name: "Cancel" })).toBeInTheDocument()
    expect(within(panel).getByRole("button", { name: "Add host" })).toBeInTheDocument()

    await openAdvancedSsh(user)
    await user.click(within(panel).getByRole("button", { name: /SSH config Host/ }))
    expect(within(panel).getByLabelText("SSH config Host")).toBeInTheDocument()
    expect(within(panel).queryByLabelText("Backend key file path")).not.toBeInTheDocument()
    expect(within(panel).queryByText("Import instructions file")).not.toBeInTheDocument()

    expect(screen.queryByText("Tags")).not.toBeInTheDocument()
    expect(screen.queryByText("Accessible paths")).not.toBeInTheDocument()
    expect(screen.queryByText("APIs and ports")).not.toBeInTheDocument()
    expect(screen.queryByText("Environment variables")).not.toBeInTheDocument()
    expect(screen.queryByText("Startup snippet")).not.toBeInTheDocument()
  })

  it("shows an empty state when the backend returns no live connections", async () => {
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    expect(await screen.findByText("No connections yet.")).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Add connection" })).toHaveLength(1)
    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
  })

  it("does not show demo connections when the live backend is unavailable", async () => {
    render(<ConnectionsPage />)

    expect(await screen.findByText("Could not load SSH connections. Check the service and try again.")).toBeInTheDocument()
    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Run check" })).not.toBeInTheDocument()
  })

  it("saves new connections through the backend", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...liveConnection,
        auth_method: "password",
        ssh_alias: null,
      },
    })

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Label"), "Live HPC")
    await user.type(within(drawer).getByLabelText("Address"), "login.live.example.org")
    await user.clear(within(drawer).getByLabelText("SSH on port"))
    await user.type(within(drawer).getByLabelText("SSH on port"), "2222")
    await user.type(within(drawer).getByLabelText("Username"), "bioflow")
    await user.type(within(drawer).getByLabelText("Password"), "secret-password")
    expect(within(drawer).queryByLabelText("SSH config Host")).not.toBeInTheDocument()
    await user.type(
      within(drawer).getByLabelText("Host Skill"),
      "Use /data/live for analysis outputs.",
    )
    await clickPanelButton(user, "Add host")

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Live HPC",
          host: "login.live.example.org",
          port: 2222,
          username: "bioflow",
          auth_method: "password",
          ssh_alias: null,
          key_path: null,
          password: "secret-password",
          private_key: null,
          passphrase: null,
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

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Address"), "login.live.example.org")
    await user.clear(within(drawer).getByLabelText("SSH on port"))
    await user.type(within(drawer).getByLabelText("SSH on port"), "22abc")
    await clickPanelButton(user, "Add host")

    expect(await screen.findByText("Port must be between 1 and 65535.")).toBeInTheDocument()
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("requires a host before saving a connection", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Label"), "Live HPC")
    await clickPanelButton(user, "Add host")

    const error = await screen.findByRole("alert")
    expect(error).toHaveTextContent("Enter an address or hostname.")
    expect(within(drawer).getByLabelText("Address")).toHaveAttribute("aria-invalid", "true")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("requires an SSH config Host before saving SSH config connections", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await openAdvancedSsh(user)
    await user.click(within(drawer).getByRole("button", { name: /SSH config Host/ }))
    await user.type(within(drawer).getByLabelText("Address"), "login.live.example.org")
    await clickPanelButton(user, "Add host")

    const error = await screen.findByRole("alert")
    expect(error).toHaveTextContent("Enter an SSH config Host.")
    expect(within(drawer).getByLabelText("SSH config Host")).toHaveAttribute("aria-invalid", "true")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("uses the SSH config Host as the saved host when Address is blank", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...liveConnection,
        host: "live-hpc",
        ssh_alias: "live-hpc",
      },
    })

    render(<ConnectionsPage />)

    const panel = await openAddConnectionPanel(user)
    await openAdvancedSsh(user)
    await user.click(within(panel).getByRole("button", { name: /SSH config Host/ }))
    await user.type(within(panel).getByLabelText("Label"), "Live HPC")
    await user.type(within(panel).getByLabelText("Username"), "bioflow")
    await user.type(within(panel).getByLabelText("SSH config Host"), "live-hpc")
    await clickPanelButton(user, "Add host")

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Live HPC",
          host: "live-hpc",
          port: 22,
          username: "bioflow",
          auth_method: "ssh_config",
          ssh_alias: "live-hpc",
          key_path: null,
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: null,
        }),
      }),
    )
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
    await openEditConnectionPanel(user)
    await clickConnectionAction(user, "Test connection")

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
    await openEditConnectionPanel(user)
    await clickConnectionAction(user, "Test connection")
    await user.click(screen.getByRole("button", { name: /^Backup HPC/ }))

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
    expect(screen.getByRole("button", { name: /^Backup HPC/ })).toHaveAttribute("aria-current", "true")
    expect(screen.getByRole("button", { name: /^Live HPC/ })).not.toHaveAttribute("aria-current")
  })

  it("keeps the detail panel aligned with the filtered connection list", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, secondConnection] })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await user.type(screen.getByLabelText("Search connections…"), "backup")

    expect(screen.getByRole("heading", { name: "Backup HPC" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Live HPC" })).not.toBeInTheDocument()

    await user.clear(screen.getByLabelText("Search connections…"))
    await user.type(screen.getByLabelText("Search connections…"), "missing")

    expect(screen.getAllByText("No matching connections. Try another name, host, alias, or note.")).not.toHaveLength(0)
    expect(screen.queryByRole("heading", { name: "Backup HPC" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Test connection" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Edit connection" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Run check" })).not.toBeInTheDocument()
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
    const drawer = await openEditConnectionPanel(user)
    expect(within(drawer).getByRole("heading", { name: "Edit host" })).toBeInTheDocument()

    await user.clear(within(drawer).getByLabelText("Label"))
    await user.type(within(drawer).getByLabelText("Label"), "Live HPC Login")
    await user.clear(within(drawer).getByLabelText("Address"))
    await user.type(within(drawer).getByLabelText("Address"), "login2.live.example.org")
    await clickPanelButton(user, "Save changes")

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
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: "Use /data/live for analysis outputs.",
        }),
      }),
    )
    expect(await screen.findByRole("heading", { name: "Live HPC Login" })).toBeInTheDocument()
  })

  it("saves edits to stored password hosts without re-entering the secret", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [passwordConnection] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...passwordConnection,
        skill_instructions: "Use /password/live for analysis checks.",
      },
    })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Password HPC" })).toBeInTheDocument()
    const drawer = await openEditConnectionPanel(user, "Password HPC")
    await user.clear(within(drawer).getByLabelText("Host Skill"))
    await user.type(within(drawer).getByLabelText("Host Skill"), "Use /password/live for analysis checks.")
    await clickPanelButton(user, "Save changes")

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections/live-connection-password", {
        method: "PATCH",
        body: JSON.stringify({
          name: "Password HPC",
          host: "password.live.example.org",
          port: 22,
          username: "bioflow",
          auth_method: "password",
          ssh_alias: null,
          key_path: null,
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: "Use /password/live for analysis checks.",
        }),
      }),
    )
  })

  it("opens the advanced SSH section when editing backend ssh-agent hosts", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [secondConnection] })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Backup HPC" })).toBeInTheDocument()
    const drawer = await openEditConnectionPanel(user, "Backup HPC")

    expect(within(drawer).getByRole("button", { name: /Backend ssh-agent/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
  })

  it("requires a key file path for key file connections", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Address"), "login.live.example.org")
    await openAdvancedSsh(user)
    await user.click(within(drawer).getByRole("button", { name: /Backend key file/ }))
    await clickPanelButton(user, "Add host")

    expect(await screen.findByText("Enter a backend-visible key file path.")).toBeInTheDocument()
    expect(within(drawer).getByLabelText("Backend key file path")).toHaveAttribute("aria-invalid", "true")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("does not send an SSH config Host for key file connections", async () => {
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

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Label"), "Key HPC")
    await user.type(within(drawer).getByLabelText("Address"), "login.key.example.org")
    await user.type(within(drawer).getByLabelText("Username"), "bioflow")
    await openAdvancedSsh(user)
    await user.click(within(drawer).getByRole("button", { name: /Backend key file/ }))
    await user.type(within(drawer).getByLabelText("Backend key file path"), "~/.ssh/id_ed25519")
    expect(within(drawer).queryByLabelText("SSH config Host")).not.toBeInTheDocument()
    await clickPanelButton(user, "Add host")

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
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: null,
        }),
      }),
    )
  })

  it("adds preset Host Skill", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await user.click(within(drawer).getByRole("button", { name: "Insert preset" }))
    await user.click(await screen.findByRole("menuitem", { name: "Nextflow HPC" }))
    expect(within(drawer).getByLabelText("Host Skill")).toHaveValue(
      "Load the site environment before diagnostics.\nRun module load nextflow when modules are available.\nCheck workflow outputs, .nextflow.log, and task directories under work/ before reruns.",
    )
  })

  it("deletes the selected connection and selects the next host", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, secondConnection] })
    apiRequestMock.mockResolvedValueOnce({ data: null })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await openEditConnectionPanel(user)
    await clickConnectionAction(user, "Delete connection")
    const dialog = screen.getByRole("dialog")
    expect(within(dialog).getByRole("heading", { name: "Delete Live HPC?" })).toBeInTheDocument()
    await user.click(within(dialog).getByRole("button", { name: "Delete" }))

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections/live-connection-1", {
        method: "DELETE",
      }),
    )
    expect(await screen.findByRole("heading", { name: "Backup HPC" })).toBeInTheDocument()
    expect(screen.queryByRole("heading", { name: "Live HPC" })).not.toBeInTheDocument()
    expect(toastSuccessMock).toHaveBeenCalledWith("Connection Live HPC deleted")
  })

  it("keeps a connection visible when deletion conflicts with remote projects", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })
    apiRequestMock.mockRejectedValueOnce(new ApiError("Remote connection is used", { status: 409 }))

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await openEditConnectionPanel(user)
    await clickConnectionAction(user, "Delete connection")
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }))

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections/live-connection-1", {
        method: "DELETE",
      }),
    )
    expect(within(screen.getByRole("dialog")).getByRole("heading", { name: "Delete Live HPC?" })).toBeInTheDocument()
    expect(toastErrorMock).toHaveBeenCalledWith(
      "Connection Live HPC is used by one or more remote projects and cannot be deleted.",
    )
  })

  it("streams a remote probe command back into the edit drawer", async () => {
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
      await openEditConnectionPanel(user)
      await clickConnectionAction(user, "Run check")

      expect(await screen.findByText("bioinfoflow-ok")).toBeInTheDocument()
      expect(buildWebSocketUrlMock).toHaveBeenCalledWith("/connections/live-connection-1/exec/ws")
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
