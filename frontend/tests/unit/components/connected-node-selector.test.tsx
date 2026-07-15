import { useState, type AnchorHTMLAttributes } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  ConnectedNodeSelector,
  LOCAL_TARGET_ID,
  type ExecutionTargetSelection,
} from "@/components/bioinfoflow/agent-runtime/connected-node-selector"
import { apiRequest } from "@/lib/api"
import type { RemoteConnection } from "@/lib/demo-connections"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const labels: Record<string, string> = {
      auto: "Auto",
      manual: "Manual",
      allTargets: "All",
      targetCount: `${values?.count ?? "0"} targets`,
      localBadge: "Local",
      selectedAutoAria: `Execution targets: Auto, ${values?.target ?? ""}`,
      selectedManualAria: `Execution targets: Manual, ${values?.target ?? ""}`,
      manage: "Manage SSH hosts",
      "local.label": "Local",
      "local.description": "Current Bioinfoflow workspace",
      "remote.label": "Remote",
      emptyRemoteHosts: "No remote hosts configured.",
      loadFailed: "Could not load remote hosts.",
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
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
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

const secondConnection: RemoteConnection = {
  ...liveConnection,
  id: "connection-live-2",
  name: "Simulation host sz01",
  host: "10.227.5.224",
  ssh_alias: "",
}

function ControlledSelector({
  initialValue = { mode: "auto" },
  onChange,
}: {
  initialValue?: ExecutionTargetSelection
  onChange?: (value: ExecutionTargetSelection) => void
}) {
  const [value, setValue] = useState<ExecutionTargetSelection>(initialValue)
  return (
    <ConnectedNodeSelector
      value={value}
      onChange={(nextValue) => {
        setValue(nextValue)
        onChange?.(nextValue)
      }}
    />
  )
}

describe("ConnectedNodeSelector", () => {
  it("defaults to Auto with a compact current-target pill", async () => {
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, secondConnection] })

    render(<ConnectedNodeSelector />)

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
    const trigger = screen.getByRole("button", {
      name: "Execution targets: Auto, All",
    })
    expect(trigger).toHaveTextContent("Auto")
    expect(screen.getByTestId("execution-current-target-pill"))
      .toHaveTextContent("All")
  })

  it("switches to Manual and emits local plus selected remote targets", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection, secondConnection] })

    render(<ControlledSelector onChange={onChange} />)

    await user.click(
      await screen.findByRole("button", {
        name: "Execution targets: Auto, All",
      }),
    )
    await user.click(screen.getByRole("menuitemradio", { name: /Manual/ }))
    await user.click(screen.getByRole("menuitemcheckbox", { name: /Live HPC/ }))

    expect(onChange).toHaveBeenLastCalledWith({
      mode: "manual",
      targetIds: [LOCAL_TARGET_ID, "connection-live-1"],
    })
  })

  it("summarizes multiple manual targets in the trigger", async () => {
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(
      <ConnectedNodeSelector
        value={{
          mode: "manual",
          targetIds: [LOCAL_TARGET_ID, "connection-live-1"],
        }}
      />,
    )

    expect(
      await screen.findByRole("button", {
        name: "Execution targets: Manual, 2 targets",
      }),
    ).toHaveTextContent("2 targets")
  })

  it("drops missing manual remote targets after connections load successfully", async () => {
    const onChange = vi.fn()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(
      <ControlledSelector
        initialValue={{
          mode: "manual",
          targetIds: [LOCAL_TARGET_ID, "missing-connection", "connection-live-1"],
        }}
        onChange={onChange}
      />,
    )

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        mode: "manual",
        targetIds: [LOCAL_TARGET_ID, "connection-live-1"],
      }),
    )
    expect(
      screen.getByRole("button", {
        name: "Execution targets: Manual, 2 targets",
      }),
    ).toBeInTheDocument()
  })

  it("falls back to local when every manual remote target is missing", async () => {
    const onChange = vi.fn()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(
      <ControlledSelector
        initialValue={{
          mode: "manual",
          targetIds: ["missing-connection"],
        }}
        onChange={onChange}
      />,
    )

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        mode: "manual",
        targetIds: [LOCAL_TARGET_ID],
      }),
    )
  })

  it("preserves stale manual remote targets when loading connections fails", async () => {
    const onChange = vi.fn()
    apiRequestMock.mockRejectedValueOnce(new Error("backend unavailable"))

    render(
      <ControlledSelector
        initialValue={{
          mode: "manual",
          targetIds: ["missing-connection"],
        }}
        onChange={onChange}
      />,
    )

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
    expect(onChange).not.toHaveBeenCalled()
    expect(
      screen.getByRole("button", {
        name: "Execution targets: Manual, Remote",
      }),
    ).toBeInTheDocument()
  })

  it("keeps Auto usable when remote hosts fail to load", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockRejectedValueOnce(new Error("backend unavailable"))

    render(<ControlledSelector />)

    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
    await user.click(screen.getByRole("button", { name: "Execution targets: Auto, All" }))
    await user.click(screen.getByRole("menuitemradio", { name: /Manual/ }))

    expect(screen.queryByText("Simulation host sz01")).not.toBeInTheDocument()
    expect(screen.getByText("Could not load remote hosts.")).toBeInTheDocument()
  })

  it("disables the execution target trigger when the composer is disabled", async () => {
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(<ConnectedNodeSelector disabled />)

    expect(screen.getByRole("button", { name: "Execution targets: Auto, All" }))
      .toBeDisabled()
    await waitFor(() => expect(apiRequestMock).toHaveBeenCalledWith("/connections"))
  })

  it("keeps the compact trigger accessible and opens the menu", async () => {
    const user = userEvent.setup()
    apiRequestMock.mockResolvedValueOnce({ data: [liveConnection] })

    render(<ConnectedNodeSelector compact />)

    const trigger = screen.getByRole("button", {
      name: "Execution targets: Auto, All",
    })
    expect(trigger).toHaveClass("max-w-9")
    expect(trigger).not.toHaveTextContent("Auto")

    await user.click(trigger)

    expect(screen.getByRole("menuitemradio", { name: "Auto" })).toBeInTheDocument()
  })
})
