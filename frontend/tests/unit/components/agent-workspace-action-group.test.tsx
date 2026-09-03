import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  AgentWorkspaceActionGroup,
  type AgentWorkspaceActionGroupProps,
} from "@/components/bioinfoflow/agent/agent-workspace-action-group"

const labels: NonNullable<AgentWorkspaceActionGroupProps["labels"]> = {
  group: "Agent workspace",
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
    ).toHaveLength(5)
    expect(
      Array.from(group.querySelectorAll<HTMLElement>("[data-workspace-action]"))
        .map((node) => node.dataset.workspaceAction),
    ).toEqual(["artifacts", "files", "dag", "browser", "panel"])
    expect(screen.queryByRole("button", { name: /subagent/i })).not.toBeInTheDocument()
  })

  it("marks the active tab and exposes a close affordance", () => {
    renderActions()

    const files = screen.getByRole("button", { name: "Open file" })
    expect(files).toHaveAttribute("aria-pressed", "true")
    expect(files.parentElement).toHaveAttribute("data-active", "true")
    expect(screen.getByRole("button", { name: "Close Open file" })).toBeInTheDocument()
  })

  it("dispatches surface actions and closes the active tab", async () => {
    const user = userEvent.setup()
    const onOpenTab = vi.fn()
    const onTogglePanel = vi.fn()
    const onCloseTab = vi.fn()
    renderActions({ onOpenTab, onTogglePanel, onCloseTab })

    await user.click(screen.getByRole("button", { name: "Artifacts" }))
    await user.click(screen.getByRole("button", { name: "DAG" }))
    await user.click(screen.getByRole("button", { name: "Browser" }))
    await user.click(screen.getByRole("button", { name: "Close workspace panel" }))
    await user.click(screen.getByRole("button", { name: "Close Open file" }))

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

  it("moves across workspace actions with arrows and Home/End", async () => {
    const user = userEvent.setup()
    renderActions()

    const artifacts = screen.getByRole("button", { name: "Artifacts" })
    const files = screen.getByRole("button", { name: "Open file" })
    const browser = screen.getByRole("button", { name: "Browser" })
    const panel = screen.getByRole("button", { name: "Close workspace panel" })

    artifacts.focus()
    await user.keyboard("{ArrowRight}")
    expect(files).toHaveFocus()
    await user.keyboard("{ArrowRight}")
    await user.keyboard("{ArrowRight}")
    expect(browser).toHaveFocus()
    await user.keyboard("{End}")
    expect(panel).toHaveFocus()
    await user.keyboard("{Home}")
    expect(artifacts).toHaveFocus()
    await user.keyboard("{ArrowLeft}")
    expect(panel).toHaveFocus()
  })

  it("returns focus to the active surface after closing it", async () => {
    const user = userEvent.setup()
    const onCloseTab = vi.fn()
    renderActions({ onCloseTab })

    const files = screen.getByRole("button", { name: "Open file" })
    const close = screen.getByRole("button", { name: "Close Open file" })
    files.focus()
    await user.click(close)

    expect(onCloseTab).toHaveBeenCalledTimes(1)
    expect(files).toHaveFocus()
  })
})
