import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { FileCode, Globe, Network, Package } from "@/lib/icons"
import {
  AgentActionGroup,
  type AgentActionCommandPort,
  type AgentActionModel,
} from "@/components/bioinfoflow/agent-action-group"

function createActions(
  activeId: AgentActionModel["id"] | null = null,
): AgentActionModel[] {
  return [
    {
      id: "browser",
      label: "Browser",
      openLabel: "Open browser",
      closeLabel: "Close browser",
      icon: Globe,
      active: activeId === "browser",
      pressed: activeId === "browser",
    },
    {
      id: "files",
      label: "Files",
      openLabel: "Open files",
      closeLabel: "Close files",
      icon: FileCode,
      active: activeId === "files",
      pressed: activeId === "files",
    },
    {
      id: "artifacts",
      label: "Artifacts",
      openLabel: "Open artifacts",
      closeLabel: "Close artifacts",
      icon: Package,
      active: activeId === "artifacts",
      pressed: activeId === "artifacts",
    },
    {
      id: "dag",
      label: "DAG",
      openLabel: "Open DAG",
      closeLabel: "Close DAG",
      icon: Network,
      active: activeId === "dag",
      pressed: activeId === "dag",
    },
  ]
}

describe("AgentActionGroup", () => {
  it("exposes each workspace surface as an independent icon action", () => {
    const commandPort: AgentActionCommandPort = { toggle: vi.fn() }

    render(
      <AgentActionGroup
        actions={createActions()}
        commandPort={commandPort}
      />,
    )

    expect(screen.getByRole("button", { name: "Open browser" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Open files" })).toHaveClass(
      "size-11",
      "min-[1025px]:size-8",
    )
    expect(screen.getByRole("button", { name: "Open artifacts" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Open DAG" })).toBeVisible()
  })

  it("routes an action click through the command port and exposes active state", async () => {
    const user = userEvent.setup()
    const commandPort: AgentActionCommandPort = { toggle: vi.fn() }

    const { rerender } = render(
      <AgentActionGroup
        actions={createActions()}
        commandPort={commandPort}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Open files" }))
    expect(commandPort.toggle).toHaveBeenCalledWith("files")

    rerender(
      <AgentActionGroup
        actions={createActions("files")}
        commandPort={commandPort}
      />,
    )

    const filesButton = screen.getByRole("button", { name: "Close files" })
    expect(filesButton).toHaveAttribute("aria-pressed", "true")
    expect(filesButton).toHaveAttribute("data-state", "active")
    expect(filesButton).toHaveAttribute("title", "Files")
    expect(filesButton).toHaveClass(
      "bg-accent",
      "text-foreground",
      "ring-1",
    )
  })
})
