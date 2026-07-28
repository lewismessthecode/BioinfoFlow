import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

import { AgentWorkspaceTabs } from "@/components/bioinfoflow/agent-runtime/agent-workspace-tabs"

describe("AgentWorkspaceTabs", () => {
  it("renders readable Codex-style workspace tabs", () => {
    render(
      <AgentWorkspaceTabs
        activeTab="preview"
        onActiveTabChange={vi.fn()}
        onClose={vi.fn()}
      />,
    )

    const tablist = screen.getByRole("tablist", { name: "sidecar.title" })
    expect(within(tablist).getByRole("tab", { name: "tabs.artifacts" })).toHaveTextContent(
      "tabs.artifacts",
    )
    expect(within(tablist).getByRole("tab", { name: "tabs.files" })).toHaveTextContent(
      "tabs.files",
    )
    expect(within(tablist).getByRole("tab", { name: "tabs.agents" })).toHaveTextContent(
      "tabs.agents",
    )
    expect(within(tablist).getByRole("tab", { name: "tabs.browser" })).toHaveTextContent(
      "tabs.browser",
    )
    expect(screen.getByRole("button", { name: "sidecar.close" })).toBeInTheDocument()
  })

  it("switches tabs with click and keyboard navigation", () => {
    const onActiveTabChange = vi.fn()
    render(
      <AgentWorkspaceTabs
        activeTab="preview"
        onActiveTabChange={onActiveTabChange}
        onClose={vi.fn()}
      />,
    )

    const artifacts = screen.getByRole("tab", { name: "tabs.artifacts" })
    fireEvent.keyDown(artifacts, { key: "ArrowRight" })
    expect(onActiveTabChange).toHaveBeenCalledWith("files")

    fireEvent.keyDown(artifacts, { key: "End" })
    expect(onActiveTabChange).toHaveBeenCalledWith("browser")

    fireEvent.click(screen.getByRole("tab", { name: "tabs.files" }))
    expect(onActiveTabChange).toHaveBeenCalledWith("files")
  })

  it("closes from the active tab without switching tabs", () => {
    const onClose = vi.fn()
    const onActiveTabChange = vi.fn()
    render(
      <AgentWorkspaceTabs
        activeTab="preview"
        onActiveTabChange={onActiveTabChange}
        onClose={onClose}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "sidecar.close" }))

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onActiveTabChange).not.toHaveBeenCalled()
  })
})
