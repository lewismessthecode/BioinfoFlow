import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentWorkspace } from "@/components/bioinfoflow/agent-runtime/agent-workspace"
import type { AgentTreeNode } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const labels: Record<string, string> = {
      "agentWorkspace.title": "Agents",
      "agentWorkspace.empty": "No agents yet",
      "agentWorkspace.listLabel": "Agent tasks",
      "agentWorkspace.detailLabel": "Agent details",
      "agentWorkspace.back": "Back to agents",
      "agentWorkspace.sessionId": "Session",
      "agentWorkspace.turnId": "Turn",
      "agentWorkspace.model": "Model",
      "agentWorkspace.requestedModel": "Requested model",
      "agentWorkspace.fallback": "Fallback",
      "agentWorkspace.terminationReason": "Termination",
      "agentWorkspace.tokenUsage": "Tokens",
      "agentWorkspace.noSummary": "No final summary",
      "agentWorkspace.runningPreview": "Working on the assigned task",
      "agentWorkspace.pendingPreview": "Preparing the child agent",
      "agentWorkspace.interruptedPreview": "Agent was interrupted",
      "agentTree.status.pending_init": "Starting",
      "agentTree.status.running": "Running",
      "agentTree.status.completed": "Completed",
      "agentTree.status.errored": "Errored",
      "agentTree.status.interrupted": "Interrupted",
    }
    return (labels[key] ?? key)
      .replace("{count}", String(values?.count ?? ""))
  },
}))

const agents: AgentTreeNode[] = [
  {
    childSessionId: "session-reader",
    childTurnId: "turn-reader",
    taskPath: "/root/reader",
    status: "completed",
    sequence: 4,
    requestedModel: "cheap-model",
    effectiveModel: "parent-model",
    modelFallback: true,
    fallbackReason: "model unavailable",
    finalText: "README inspected successfully.",
    terminationReason: "assistant_final",
    tokenUsage: { total_tokens: 321 },
  },
  {
    childSessionId: "session-reviewer",
    childTurnId: "turn-reviewer",
    taskPath: "/root/reviewer",
    status: "errored",
    sequence: 5,
    effectiveModel: "parent-model",
    errorMessage: "Provider request failed.",
  },
]

describe("AgentWorkspace", () => {
  it("renders a flat desktop list and details the selected agent", () => {
    render(<AgentWorkspace agents={agents} variant="desktop" />)

    const list = screen.getByRole("listbox", { name: "Agent tasks" })
    const options = within(list).getAllByRole("option")
    expect(options).toHaveLength(2)
    expect(options[0]).toHaveAttribute("aria-selected", "true")
    expect(options[0].className).toContain("bg-muted")
    expect(options[0].className).not.toMatch(/border-l|before:/)

    const detail = screen.getByRole("region", { name: "Agent details" })
    expect(within(detail).getByText("/root/reader")).toBeInTheDocument()
    expect(within(detail).getByText("README inspected successfully.")).toBeInTheDocument()
    expect(within(detail).getByText("cheap-model")).toBeInTheDocument()
    expect(within(detail).getByText("parent-model")).toBeInTheDocument()
    expect(within(detail).getByText("321")).toBeInTheDocument()

    fireEvent.click(options[1])
    expect(options[1]).toHaveAttribute("aria-selected", "true")
    expect(within(detail).getByText("Provider request failed.")).toBeInTheDocument()
  })

  it("uses list to detail navigation on mobile and restores the list", () => {
    render(<AgentWorkspace agents={agents} variant="mobile" />)

    expect(screen.getByRole("listbox", { name: "Agent tasks" })).toBeInTheDocument()
    expect(screen.queryByRole("region", { name: "Agent details" })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("option", { name: /reader/i }))
    expect(screen.queryByRole("listbox", { name: "Agent tasks" })).not.toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Agent details" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Back to agents" }))
    expect(screen.getByRole("listbox", { name: "Agent tasks" })).toBeInTheDocument()
  })

  it("supports keyboard selection and an empty state", () => {
    const { rerender } = render(<AgentWorkspace agents={agents} variant="desktop" />)
    const options = screen.getAllByRole("option")
    fireEvent.keyDown(options[0], { key: "ArrowDown" })
    expect(options[1]).toHaveFocus()
    fireEvent.keyDown(options[1], { key: "Enter" })
    expect(options[1]).toHaveAttribute("aria-selected", "true")

    rerender(<AgentWorkspace agents={[]} variant="desktop" />)
    expect(screen.getByText("No agents yet")).toBeInTheDocument()
  })
})
