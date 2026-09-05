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
  files: "Files",
  dag: "DAG",
  browser: "Browser",
  openPanel: "Open workspace panel",
  closePanel: "Close workspace panel",
  closeTab: "Close Files",
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
    expect(group.querySelector("[data-workspace-divider]")).toBeTruthy()
    expect(group.querySelector("[data-workspace-divider]")?.previousElementSibling)
      .toBe(group.querySelector("[data-workspace-tabs]"))
    expect(group.querySelector("[data-workspace-divider]")?.nextElementSibling)
      .toBe(group.querySelector('[data-workspace-action="panel"]'))
    expect(screen.queryByRole("button", { name: /subagent/i })).not.toBeInTheDocument()
  })

  it("places the selected workspace file in the global action row", async () => {
    const user = userEvent.setup()
    const onOpenSelectedFile = vi.fn()
    const onCloseSelectedFile = vi.fn()
    renderActions({
      selectedFile: { name: "rnaseq.wdl", path: "workflows/rnaseq.wdl" },
      onOpenSelectedFile,
      onCloseSelectedFile,
    })

    const fileTab = screen.getByRole("button", { name: "rnaseq.wdl" })
    expect(fileTab).toHaveAttribute("aria-pressed", "true")
    expect(fileTab).toHaveAttribute("title", "workflows/rnaseq.wdl")
    expect(fileTab).toHaveClass("max-sm:w-8", "max-sm:justify-center")
    expect(fileTab.querySelector("span")).toHaveClass("max-sm:hidden")
    expect(screen.getByRole("button", { name: "Close rnaseq.wdl" })).toHaveClass(
      "max-sm:mr-0",
    )
    const actionOrder = Array.from(
      screen
        .getByRole("group", { name: "Agent workspace" })
        .querySelectorAll<HTMLElement>("[data-workspace-action]"),
    ).map((node) => node.dataset.workspaceAction)
    expect(actionOrder).toEqual([
      "artifacts",
      "files",
      "file",
      "dag",
      "browser",
      "panel",
    ])
    expect(screen.getByRole("button", { name: "Files" })).toHaveAttribute(
      "aria-pressed",
      "true",
    )
    expect(screen.getByRole("button", { name: "Files" }).parentElement).toHaveAttribute(
      "data-active",
      "false",
    )
    expect(fileTab.parentElement).toHaveAttribute("data-active", "true")
    await user.click(fileTab)
    expect(onOpenSelectedFile).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole("button", { name: "Close rnaseq.wdl" }))
    expect(onCloseSelectedFile).toHaveBeenCalledTimes(1)
  })

  it("keeps compact labels discoverable without allowing the action row to overflow", () => {
    renderActions()

    const group = screen.getByRole("group", { name: "Agent workspace" })
    expect(group).toHaveClass("max-w-full", "overflow-hidden", "flex-nowrap")
    expect(group.querySelector("[data-workspace-tabs]")).toHaveClass(
      "min-w-0",
      "overflow-hidden",
      "flex-nowrap",
    )

    for (const label of ["Artifacts", "Files", "DAG", "Browser"]) {
      const button = screen.getByRole("button", { name: label })
      expect(button).toHaveAttribute("title", label)
      expect(button).toHaveClass("min-w-0", "shrink-0")
      expect(button.querySelector("span")).toHaveClass("hidden", "xl:inline")
    }
  })

  it("marks the active tab and exposes a close affordance", () => {
    renderActions()

    const files = screen.getByRole("button", { name: "Files" })
    expect(files).toHaveAttribute("aria-pressed", "true")
    expect(files.parentElement).toHaveAttribute("data-active", "true")
    expect(screen.getByRole("button", { name: "Close Files" })).toBeInTheDocument()
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
    await user.click(screen.getByRole("button", { name: "Close Files" }))

    expect(onOpenTab).toHaveBeenNthCalledWith(1, "artifacts")
    expect(onOpenTab).toHaveBeenNthCalledWith(2, "dag")
    expect(onOpenTab).toHaveBeenNthCalledWith(3, "browser")
    expect(onTogglePanel).toHaveBeenCalledTimes(1)
    expect(onCloseTab).toHaveBeenCalledTimes(1)
  })

  it("uses the open-panel label and no tab close when the panel is closed", () => {
    renderActions({ panelOpen: false, activeTab: null })

    expect(screen.getByRole("button", { name: "Open workspace panel" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Close Files" })).not.toBeInTheDocument()
  })

  it("moves across workspace actions with arrows and Home/End", async () => {
    const user = userEvent.setup()
    renderActions()

    const artifacts = screen.getByRole("button", { name: "Artifacts" })
    const files = screen.getByRole("button", { name: "Files" })
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

  it("includes the selected file in the keyboard action order", async () => {
    const user = userEvent.setup()
    renderActions({
      selectedFile: { name: "rnaseq.wdl", path: "workflows/rnaseq.wdl" },
    })

    const files = screen.getByRole("button", { name: "Files" })
    const file = screen.getByRole("button", { name: "rnaseq.wdl" })
    const dag = screen.getByRole("button", { name: "DAG" })

    files.focus()
    await user.keyboard("{ArrowRight}")
    expect(file).toHaveFocus()
    await user.keyboard("{ArrowRight}")
    expect(dag).toHaveFocus()
    await user.keyboard("{ArrowLeft}")
    expect(file).toHaveFocus()
  })

  it("returns focus to the active surface after closing it", async () => {
    const user = userEvent.setup()
    const onCloseTab = vi.fn()
    renderActions({ onCloseTab })

    const files = screen.getByRole("button", { name: "Files" })
    const close = screen.getByRole("button", { name: "Close Files" })
    files.focus()
    await user.click(close)

    expect(onCloseTab).toHaveBeenCalledTimes(1)
    expect(files).toHaveFocus()
  })
})
