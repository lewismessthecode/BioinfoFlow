import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  AgentWorkspaceActionGroup,
  type AgentWorkspaceActionGroupProps,
} from "@/components/bioinfoflow/agent/agent-workspace-action-group"

const labels: NonNullable<AgentWorkspaceActionGroupProps["labels"]> = {
  group: "Agent workspace",
  more: "More preferences",
  terminal: "Terminal",
  artifacts: "Artifacts",
  files: "Open file",
  dag: "DAG",
  browser: "Browser",
  openPanel: "Open workspace panel",
  closePanel: "Close workspace panel",
  closeTab: "Close Open file",
}

function renderActions(
  overrides: Partial<AgentWorkspaceActionGroupProps> = {},
) {
  return render(
    <AgentWorkspaceActionGroup
      labels={labels}
      activeTab="files"
      panelOpen
      onMore={vi.fn()}
      onToggleTerminal={vi.fn()}
      onOpenTab={vi.fn()}
      onTogglePanel={vi.fn()}
      onCloseTab={vi.fn()}
      {...overrides}
    />,
  )
}

describe("AgentWorkspaceActionGroup", () => {
  it("renders the screenshot action order without a Subagents entry", () => {
    renderActions()

    const group = screen.getByRole("group", { name: "Agent workspace" })
    expect(
      Array.from(group.querySelectorAll<HTMLElement>("[data-workspace-action]")),
    ).toHaveLength(7)
    expect(
      Array.from(group.querySelectorAll<HTMLElement>("[data-workspace-action]"))
        .map((node) => node.dataset.workspaceAction),
    ).toEqual(["more", "terminal", "artifacts", "files", "dag", "browser", "panel"])
    expect(screen.queryByRole("button", { name: /subagent/i })).not.toBeInTheDocument()
  })

  it("marks the active tab and exposes a close affordance", () => {
    renderActions()

    const files = screen.getByRole("button", { name: "Open file" })
    expect(files).toHaveAttribute("aria-pressed", "true")
    expect(files.parentElement).toHaveAttribute("data-active", "true")
    expect(screen.getByRole("button", { name: "Close Open file" })).toBeInTheDocument()
  })

  it("dispatches top-level actions and closes the active tab", async () => {
    const user = userEvent.setup()
    const onMore = vi.fn()
    const onToggleTerminal = vi.fn()
    const onOpenTab = vi.fn()
    const onTogglePanel = vi.fn()
    const onCloseTab = vi.fn()
    renderActions({ onMore, onToggleTerminal, onOpenTab, onTogglePanel, onCloseTab })

    await user.click(screen.getByRole("button", { name: "More preferences" }))
    await user.click(screen.getByRole("button", { name: "Terminal" }))
    await user.click(screen.getByRole("button", { name: "Artifacts" }))
    await user.click(screen.getByRole("button", { name: "DAG" }))
    await user.click(screen.getByRole("button", { name: "Browser" }))
    await user.click(screen.getByRole("button", { name: "Close workspace panel" }))
    await user.click(screen.getByRole("button", { name: "Close Open file" }))

    expect(onMore).toHaveBeenCalledTimes(1)
    expect(onToggleTerminal).toHaveBeenCalledTimes(1)
    expect(onOpenTab).toHaveBeenNthCalledWith(1, "artifacts")
    expect(onOpenTab).toHaveBeenNthCalledWith(2, "dag")
    expect(onOpenTab).toHaveBeenNthCalledWith(3, "browser")
    expect(onTogglePanel).toHaveBeenCalledTimes(1)
    expect(onCloseTab).toHaveBeenCalledTimes(1)
  })

  it("uses the open-panel label and no tab close when the panel is closed", () => {
    renderActions({ panelOpen: false, activeTab: null })

    expect(screen.getByRole("button", { name: "Open workspace panel" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Close Open file" })).not.toBeInTheDocument()
  })
})
