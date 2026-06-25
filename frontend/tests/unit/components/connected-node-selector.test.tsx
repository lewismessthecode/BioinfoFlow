import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ConnectedNodeSelector } from "@/components/bioinfoflow/agent-runtime/connected-node-selector"
import { apiRequest } from "@/lib/api"
import type { RemoteConnection } from "@/lib/demo-connections"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      placeholder: "Choose connection",
      selectedAria: "Selected remote connection",
      menuTitle: "Remote connections",
      manage: "Manage connections",
      "status.online": "Online",
      "status.offline": "Offline",
      "status.error": "Connection error",
      "status.unknown": "Not tested",
    }
    return labels[key] ?? key
  },
}))

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
}))

const apiRequestMock = vi.mocked(apiRequest)

const liveConnection: RemoteConnection = {
  id: "connection-live-1",
  name: "Live HPC",
  host: "login.live.example.org",
  port: 22,
  username: "bioflow",
  auth_method: "ssh_config",
  ssh_alias: "live-hpc",
  key_path: "",
  status: "online",
  skill_instructions: "Use /data/live.",
}

describe("ConnectedNodeSelector", () => {
  it("keeps an empty controlled selection empty after live connections load", async () => {
    const onSelectedConnectionChange = vi.fn()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(
      <ConnectedNodeSelector
        selectedConnectionId=""
        onSelectedConnectionChange={onSelectedConnectionChange}
      />,
    )

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
    expect(screen.getByRole("button", { name: "Choose connection" })).toBeInTheDocument()
    expect(onSelectedConnectionChange).not.toHaveBeenCalled()
  })

  it("does not clear a restored backend id before live connections load", async () => {
    const onSelectedConnectionChange = vi.fn()
    apiRequestMock.mockReturnValueOnce(new Promise(() => {}))

    render(
      <ConnectedNodeSelector
        selectedConnectionId="11111111-1111-1111-1111-111111111111"
        onSelectedConnectionChange={onSelectedConnectionChange}
      />,
    )

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
    expect(screen.getByRole("button", { name: "Choose connection" })).toBeInTheDocument()
    expect(onSelectedConnectionChange).not.toHaveBeenCalled()
  })

  it("clears a stale controlled selection", async () => {
    const onSelectedConnectionChange = vi.fn()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(
      <ConnectedNodeSelector
        selectedConnectionId="missing-connection"
        onSelectedConnectionChange={onSelectedConnectionChange}
      />,
    )

    await waitFor(() => expect(onSelectedConnectionChange).toHaveBeenCalledWith(""))
  })

  it("does not expose demo connections when the live connection request fails", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockRejectedValueOnce(new Error("backend unavailable"))

    render(<ConnectedNodeSelector />)

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
    await user.click(screen.getByRole("button", { name: "Choose connection" }))

    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
    expect(screen.queryByText("Test host sz03")).not.toBeInTheDocument()
  })
})
