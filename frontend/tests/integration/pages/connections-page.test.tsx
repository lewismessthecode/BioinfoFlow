import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import ConnectionsPage from "@/app/(app)/connections/page"
import { apiRequest } from "@/lib/api"
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
  getApiErrorMessage: (error: unknown, fallback: string) =>
    error instanceof Error ? error.message : fallback,
}))

const apiRequestMock = vi.mocked(apiRequest)

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

describe("ConnectionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiRequestMock.mockRejectedValue(new Error("backend unavailable"))
  })

  it("focuses the main flow on SSH config and Agent Skill instructions", async () => {
    const user = userEvent.setup()

    render(<ConnectionsPage />)

    expect(screen.getByRole("heading", { name: "Connection Center" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Add connection" }))

    expect(screen.getByLabelText("SSH alias")).toBeInTheDocument()
    expect(screen.getByLabelText("Private key path")).toBeInTheDocument()
    expect(screen.getAllByText("Agent Skill instructions")[0]).toBeInTheDocument()
    expect(
      screen.getAllByText("Put paths, APIs, environment notes, and startup commands in the skill text.")[0],
    ).toBeInTheDocument()

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
      await screen.findByText("No matching connections. Try another name, host, alias, or note."),
    ).toBeInTheDocument()
    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
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
      screen.getByLabelText("Agent Skill instructions"),
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
    expect(error).toHaveTextContent("SSH alias is required for SSH config auth.")
    expect(screen.getByLabelText("SSH alias")).toHaveAttribute("aria-invalid", "true")
    expect(apiRequestMock).toHaveBeenCalledTimes(1)
  })
})
