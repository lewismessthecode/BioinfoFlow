import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentWorkspaceActionGroup, type AgentWorkspaceActionGroupProps } from "@/components/bioinfoflow/agent/agent-workspace-action-group"

const labels: AgentWorkspaceActionGroupProps["labels"] = {
  group: "Agent workspace", addTab: "Add tab", artifacts: "Artifacts", files: "Files", dag: "DAG", browser: "Browser", openPanel: "Show drawer", closePanel: "Hide drawer",
}

function renderActions(overrides: Partial<AgentWorkspaceActionGroupProps> = {}) {
  return render(<AgentWorkspaceActionGroup labels={labels} panelOpen={false} onOpenTab={vi.fn()} onTogglePanel={vi.fn()} {...overrides} />)
}

describe("AgentWorkspaceActionGroup", () => {
  it("lets people add a drawer tab from a single plus menu", async () => {
    const user = userEvent.setup(); const onOpenTab = vi.fn(); renderActions({ onOpenTab })
    expect(screen.getByRole("button", { name: "Add tab" })).toBeVisible()
    expect(screen.queryByRole("button", { name: "Artifacts" })).not.toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Add tab" }))
    await user.click(screen.getByRole("menuitem", { name: "Files" }))
    expect(onOpenTab).toHaveBeenCalledWith("workspace")
  })

  it("keeps the far-right control exclusively for showing and hiding the drawer", async () => {
    const user = userEvent.setup(); const onTogglePanel = vi.fn(); renderActions({ panelOpen: true, onTogglePanel })
    const drawerControl = screen.getByRole("button", { name: "Hide drawer" })
    expect(drawerControl).toHaveAttribute("aria-pressed", "true")
    await user.click(drawerControl)
    expect(onTogglePanel).toHaveBeenCalledOnce()
  })
})
