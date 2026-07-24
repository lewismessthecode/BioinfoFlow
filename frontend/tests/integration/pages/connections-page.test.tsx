import { act, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { toast } from "sonner"

import ConnectionsPage from "@/app/(app)/connections/page"
import { ApiError, apiRequest, buildWebSocketUrl } from "@/lib/api"
import type { RemoteConnection } from "@/lib/demo-connections"
import enMessages from "@/messages/en.json"

HTMLElement.prototype.hasPointerCapture = vi.fn(() => false)
HTMLElement.prototype.setPointerCapture = vi.fn()
HTMLElement.prototype.releasePointerCapture = vi.fn()
Element.prototype.scrollIntoView = vi.fn()

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
  jump_connection_id: null,
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
  jump_connection_id: null,
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
  jump_connection_id: null,
  ssh_alias: "",
  key_path: "",
  status: "unknown",
  skill_instructions: "Use /password/live for checks.",
}

const jumpConnection: RemoteConnection = {
  id: "live-connection-jump",
  name: "HALOS",
  host: "halos.internal",
  port: 22,
  username: "halos-user",
  auth_method: "jump",
  jump_connection_id: liveConnection.id,
  ssh_alias: "",
  key_path: "",
  status: "unknown",
  skill_instructions: "Use HALOS for protected analysis workloads.",
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

  it("keeps SSH connection cards focused on host identity and status", async () => {
    apiRequestMock.mockResolvedValueOnce({
      data: [
        {
          ...liveConnection,
          status: "online",
          last_checked_at: "2026-06-25T10:11:12Z",
        },
      ],
    })

    render(<ConnectionsPage />)

    const card = await screen.findByRole("button", { name: /^Live HPC/ })
    expect(card).toHaveTextContent("Live HPC")
    expect(card).toHaveTextContent("bioflow@login.live.example.org")
    expect(card).toHaveTextContent("Online")
    expect(card).not.toHaveTextContent("SSH config Host")
    expect(card).not.toHaveTextContent("live-hpc")
    expect(card).not.toHaveTextContent(/Jun 25|10:11|18:11/)
  })

  it("keeps long SSH connection identities inside the fixed card text area", async () => {
    const longConnection = {
      ...liveConnection,
      name: "华东生产测序集群超长登录节点名称 simulation login node sz01",
      username: "bioinformatics-production-user",
      host: "extremely-long-login-node-name-for-production-sequencing-cluster.example.org",
    }
    apiRequestMock.mockResolvedValueOnce({ data: [longConnection] })

    render(<ConnectionsPage />)

    const card = await screen.findByRole("button", {
      name: /^华东生产测序集群超长登录节点名称/,
    })
    const title = within(card).getByRole("heading", { name: longConnection.name })
    const identity = within(card).getByText(
      `${longConnection.username}@${longConnection.host}`,
    )

    expect(title).toHaveClass("truncate")
    expect(identity).toHaveClass("truncate")
    expect(title).toHaveAttribute("title", longConnection.name)
    expect(identity).toHaveAttribute(
      "title",
      `${longConnection.username}@${longConnection.host}`,
    )
  })

  it("keeps selected and connecting cards on stable geometry", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })
    apiRequestMock.mockImplementationOnce(() => new Promise(() => {}))

    render(<ConnectionsPage />)

    const cardButton = await screen.findByRole("button", { name: /^Live HPC/ })
    await user.click(cardButton)
    await openEditConnectionPanel(user)
    await clickConnectionAction(user, "Retest connection")

    const article = cardButton.closest("article")
    expect(article).toHaveClass("box-border", "h-[108px]", "ring-inset")
    expect(cardButton).toHaveClass("grid-cols-[44px_minmax(0,1fr)_6rem]")
    expect(within(cardButton).getByText("Connecting…").closest("span")).toHaveClass(
      "w-24",
      "justify-center",
    )
  })

  it("offers direct and jump routes while excluding jump and edited candidates", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({
      data: [
        liveConnection,
        secondConnection,
        { ...jumpConnection, jump_connection_id: secondConnection.id },
      ],
    })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await openEditConnectionPanel(user)
    const panel = getConnectionPanel()
    expect(within(panel).getByText("Connection route")).toBeInTheDocument()
    expect(within(panel).getByRole("group", { name: "Connection route" })).toBeInTheDocument()
    expect(within(panel).getByRole("button", { name: /Direct/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )

    await user.click(within(panel).getByRole("button", { name: /Via jump host/ }))
    const selector = within(panel).getByRole("combobox", { name: "Saved jump host" })
    selector.focus()
    await user.keyboard("{ArrowDown}")
    expect(await screen.findByRole("option", { name: "Backup HPC" })).toBeInTheDocument()
    expect(screen.queryByRole("option", { name: "Live HPC" })).not.toBeInTheDocument()
    expect(screen.queryByRole("option", { name: "HALOS" })).not.toBeInTheDocument()
    expect(within(panel).queryByText("Authentication")).not.toBeInTheDocument()
    expect(within(panel).getByText(/logs into that host first/)).toBeInTheDocument()
  })

  it("restores a direct private-key draft after exploring the jump route", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(<ConnectionsPage />)

    const panel = await openAddConnectionPanel(user)
    await user.click(within(panel).getByRole("button", { name: /^Private key/ }))
    await user.type(within(panel).getByLabelText("Private key"), "private-key-draft")
    await user.type(within(panel).getByLabelText("Passphrase"), "draft-passphrase")

    await user.click(within(panel).getByRole("button", { name: /Via jump host/ }))
    await user.click(within(panel).getByRole("button", { name: /^Direct/ }))

    expect(within(panel).getByRole("button", { name: /^Private key/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    expect(within(panel).getByLabelText("Private key")).toHaveValue("private-key-draft")
    expect(within(panel).getByLabelText("Passphrase")).toHaveValue("draft-passphrase")
  })

  it("prevents converting a direct connection that is used as a jump host", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, jumpConnection] })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    const panel = await openEditConnectionPanel(user)
    expect(within(panel).getByRole("button", { name: /Via jump host/ })).toBeDisabled()
    expect(
      within(panel).getByText(
        "This connection is used as a jump host. Update dependent connections before changing its route.",
      ),
    ).toBeInTheDocument()
  })

  it("shows an accessible empty state when no direct jump candidates exist", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [jumpConnection] })

    render(<ConnectionsPage />)

    await openAddConnectionPanel(user)
    await user.click(within(getConnectionPanel()).getByRole("button", { name: /Via jump host/ }))

    expect(within(getConnectionPanel()).getByText("No direct connections are available as jump hosts.")).toBeInTheDocument()
    expect(within(getConnectionPanel()).queryByRole("combobox", { name: "Saved jump host" })).not.toBeInTheDocument()
  })

  it("requires a saved jump host before saving", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(<ConnectionsPage />)

    const panel = await openAddConnectionPanel(user)
    await user.click(within(panel).getByRole("button", { name: /Via jump host/ }))
    await user.type(within(panel).getByLabelText("Address"), "halos.internal")
    await clickPanelButton(user, "Add host")

    expect(await screen.findByRole("alert")).toHaveTextContent("Select a saved jump host.")
    expect(within(panel).getByRole("combobox", { name: "Saved jump host" })).toHaveAttribute(
      "aria-invalid",
      "true",
    )
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("saves HALOS through Simulation environment with cleared direct credentials", async () => {
    const user = userEvent.setup()
    const simulationEnvironment = { ...liveConnection, name: "Simulation environment" }
    apiRequestMock.mockResolvedValueOnce({ data: [simulationEnvironment] })
    apiRequestMock.mockResolvedValueOnce({ data: jumpConnection })

    render(<ConnectionsPage />)

    const panel = await openAddConnectionPanel(user)
    await user.type(within(panel).getByLabelText("Label"), "HALOS")
    await user.type(within(panel).getByLabelText("Address"), "halos.internal")
    await user.type(within(panel).getByLabelText("Username"), "halos-user")
    await user.click(within(panel).getByRole("button", { name: /Via jump host/ }))
    const selector = within(panel).getByRole("combobox", { name: "Saved jump host" })
    selector.focus()
    await user.keyboard("{ArrowDown}{Enter}")
    await clickPanelButton(user, "Add host")

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "HALOS",
          host: "halos.internal",
          port: 22,
          username: "halos-user",
          auth_method: "jump",
          jump_connection_id: liveConnection.id,
          ssh_alias: null,
          key_path: null,
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: null,
        }),
      }),
    )
  })

  it("hydrates and patches an existing jump connection", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, jumpConnection] })
    apiRequestMock.mockResolvedValueOnce({ data: jumpConnection })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "HALOS" })).toBeInTheDocument()
    const panel = await openEditConnectionPanel(user, "HALOS")
    expect(within(panel).getByRole("button", { name: /Via jump host/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    expect(within(panel).getByRole("combobox", { name: "Saved jump host" })).toHaveTextContent(
      "Live HPC",
    )
    await clickPanelButton(user, "Save changes")

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenCalledWith("/connections/live-connection-jump", {
        method: "PATCH",
        body: JSON.stringify({
          name: "HALOS",
          host: "halos.internal",
          port: 22,
          username: "halos-user",
          auth_method: "jump",
          jump_connection_id: liveConnection.id,
          ssh_alias: null,
          key_path: null,
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: "Use HALOS for protected analysis workloads.",
        }),
      }),
    )
  })

  it("clears the jump id and restores password requirements when switching to direct", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, jumpConnection] })

    render(<ConnectionsPage />)

    expect(await screen.findByRole("heading", { name: "HALOS" })).toBeInTheDocument()
    const panel = await openEditConnectionPanel(user, "HALOS")
    await user.click(within(panel).getByRole("button", { name: /^Direct/ }))
    expect(within(panel).getByLabelText("Password")).toBeInTheDocument()
    await clickPanelButton(user, "Save changes")
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter the SSH password.")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })

  it("shows resolved jump route metadata on the target card and includes it in search", async () => {
    const user = userEvent.setup()
    const simulationEnvironment = { ...liveConnection, name: "Simulation environment" }
    apiRequestMock.mockResolvedValueOnce({ data: [simulationEnvironment, jumpConnection] })

    render(<ConnectionsPage />)

    const targetCard = await screen.findByRole("button", { name: /^HALOS/ })
    expect(targetCard).toHaveTextContent("halos-user@halos.internal")
    expect(targetCard).toHaveTextContent("via Simulation environment")
    await user.type(screen.getByLabelText("Search connections…"), "simulation environment")
    expect(screen.getByRole("button", { name: /^HALOS/ })).toBeInTheDocument()
  })

  it("exposes the full truncated jump route as a title", async () => {
    const longJumpName = "上海生信模拟环境超长跳板主机名称 Simulation environment"
    const longIdentity = "halos-production-user@halos-production-login.internal.example.org"
    apiRequestMock.mockResolvedValueOnce({
      data: [
        { ...liveConnection, name: longJumpName },
        {
          ...jumpConnection,
          username: "halos-production-user",
          host: "halos-production-login.internal.example.org",
        },
      ],
    })

    render(<ConnectionsPage />)

    const targetCard = await screen.findByRole("button", { name: /^HALOS/ })
    expect(within(targetCard).getByText(longIdentity)).toHaveAttribute("title", longIdentity)
    expect(within(targetCard).getByText(`via ${longJumpName}`)).toHaveAttribute(
      "title",
      `via ${longJumpName}`,
    )
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
      expect(apiRequestMock).toHaveBeenCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Live HPC",
          host: "login.live.example.org",
          port: 2222,
          username: "bioflow",
          auth_method: "password",
          jump_connection_id: null,
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

  it("automatically verifies a newly saved SSH connection", async () => {
    const user = userEvent.setup()
    let resolveTest: (value: unknown) => void = () => {}
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...liveConnection,
        auth_method: "password",
        ssh_alias: null,
      },
    })
    apiRequestMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveTest = resolve
        }),
    )

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Label"), "Live HPC")
    await user.type(within(drawer).getByLabelText("Address"), "login.live.example.org")
    await user.type(within(drawer).getByLabelText("Username"), "bioflow")
    await user.type(within(drawer).getByLabelText("Password"), "secret-password")
    await clickPanelButton(user, "Add host")

    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenLastCalledWith("/connections/live-connection-1/test", {
        method: "POST",
      }),
    )
    expect(screen.getByText("Connecting…")).toBeInTheDocument()

    resolveTest({
      data: {
        status: "online",
        error: null,
        checked_at: "2026-06-25T10:11:12Z",
        connection: {
          ...liveConnection,
          auth_method: "password",
          last_status: "online",
          last_error: null,
          last_checked_at: "2026-06-25T10:11:12Z",
        },
      },
    })

    expect(await screen.findByText("Online")).toBeInTheDocument()
  })

  it("keeps a newly saved host when automatic verification fails", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    apiRequestMock.mockResolvedValueOnce({
      data: {
        ...liveConnection,
        auth_method: "password",
        ssh_alias: null,
      },
    })
    apiRequestMock.mockRejectedValueOnce(new Error("SSH authentication failed"))

    render(<ConnectionsPage />)

    const drawer = await openAddConnectionPanel(user)
    await user.type(within(drawer).getByLabelText("Label"), "Live HPC")
    await user.type(within(drawer).getByLabelText("Address"), "login.live.example.org")
    await user.type(within(drawer).getByLabelText("Username"), "bioflow")
    await user.type(within(drawer).getByLabelText("Password"), "secret-password")
    await clickPanelButton(user, "Add host")

    expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith("SSH authentication failed"))
    expect(screen.queryByText("Connecting…")).not.toBeInTheDocument()
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
      expect(apiRequestMock).toHaveBeenCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Live HPC",
          host: "live-hpc",
          port: 22,
          username: "bioflow",
          auth_method: "ssh_config",
          jump_connection_id: null,
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
    await clickConnectionAction(user, "Retest connection")

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
    await clickConnectionAction(user, "Retest connection")
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
    expect(screen.queryByRole("button", { name: "Retest connection" })).not.toBeInTheDocument()
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
    apiRequestMock.mockResolvedValueOnce({
      data: {
        status: "online",
        error: null,
        checked_at: "2026-06-25T10:11:12Z",
        connection: {
          ...liveConnection,
          name: "Live HPC Login",
          host: "login2.live.example.org",
          last_status: "online",
        },
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
      expect(apiRequestMock).toHaveBeenCalledWith("/connections/live-connection-1", {
        method: "PATCH",
        body: JSON.stringify({
          name: "Live HPC Login",
          host: "login2.live.example.org",
          port: 2222,
          username: "bioflow",
          auth_method: "ssh_config",
          jump_connection_id: null,
          ssh_alias: "live-hpc",
          key_path: null,
          password: null,
          private_key: null,
          passphrase: null,
          skill_instructions: "Use /data/live for analysis outputs.",
        }),
      }),
    )
    await waitFor(() =>
      expect(apiRequestMock).toHaveBeenCalledWith("/connections/live-connection-1/test", {
        method: "POST",
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
      expect(apiRequestMock).toHaveBeenCalledWith("/connections/live-connection-password", {
        method: "PATCH",
        body: JSON.stringify({
          name: "Password HPC",
          host: "password.live.example.org",
          port: 22,
          username: "bioflow",
          auth_method: "password",
          jump_connection_id: null,
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
      expect(apiRequestMock).toHaveBeenCalledWith("/connections", {
        method: "POST",
        body: JSON.stringify({
          name: "Key HPC",
          host: "login.key.example.org",
          port: 22,
          username: "bioflow",
          auth_method: "key_file",
          jump_connection_id: null,
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

  it("keeps run-check progress and completion visible after the action menu closes", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    class ControlledWebSocket {
      static OPEN = 1
      static instance: ControlledWebSocket | null = null
      readyState = ControlledWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null

      constructor(readonly url: string) {
        ControlledWebSocket.instance = this
        queueMicrotask(() => this.onopen?.())
      }

      send() {}
      close() {}
    }

    vi.stubGlobal("WebSocket", ControlledWebSocket)
    try {
      render(<ConnectionsPage />)

      expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
      await openEditConnectionPanel(user)
      await clickConnectionAction(user, "Run check")

      expect(await screen.findByText("Running connection check…")).toBeInTheDocument()
      expect(screen.queryByRole("menu")).not.toBeInTheDocument()

      await act(async () => {
        ControlledWebSocket.instance?.onmessage?.({
          data: JSON.stringify({ type: "stdout", data: "bioinfoflow-ok\n" }),
        } as MessageEvent)
        ControlledWebSocket.instance?.onmessage?.({
          data: JSON.stringify({ type: "exit", exit_code: 0 }),
        } as MessageEvent)
      })

      expect(await screen.findByText("Connection check completed.")).toBeInTheDocument()
      expect(screen.getByText("bioinfoflow-ok")).toBeInTheDocument()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("shows a persistent alert when a run check fails", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    class FailingWebSocket {
      static OPEN = 1
      readyState = FailingWebSocket.OPEN
      onopen: (() => void) | null = null
      onmessage: ((event: MessageEvent) => void) | null = null
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null

      constructor(readonly url: string) {
        queueMicrotask(() => this.onopen?.())
        queueMicrotask(() =>
          this.onmessage?.({
            data: JSON.stringify({ type: "error", message: "Remote command refused" }),
          } as MessageEvent),
        )
      }

      send() {}
      close() {}
    }

    vi.stubGlobal("WebSocket", FailingWebSocket)
    try {
      render(<ConnectionsPage />)

      expect(await screen.findByRole("heading", { name: "Live HPC" })).toBeInTheDocument()
      await openEditConnectionPanel(user)
      await clickConnectionAction(user, "Run check")

      const alert = await screen.findByRole("alert")
      expect(alert).toHaveTextContent("Remote command refused")
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
