import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTodoDock } from "@/components/bioinfoflow/agent-runtime/agent-todo-dock"
import { deriveTodoDisplayItems, type AgentRuntimeTurn, type AgentTodoDisplayItem } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    const labels: Record<string, string> = {
      "progress.tasks": "Tasks",
      "progress.empty": "No tasks yet",
      "todoDock.collapse": "Collapse task dock",
      "todoDock.expand": "Expand task dock",
      "todoDock.summary": `${values?.count ?? 0} tasks left`,
    }
    return labels[key] ?? key
  },
}))

const items: AgentTodoDisplayItem[] = [
  { content: "Read the code", status: "completed", displayStatus: "completed" },
  {
    content: "Make the change",
    status: "in_progress",
    activeForm: "Editing",
    displayStatus: "in_progress",
  },
]

const failedTurn: AgentRuntimeTurn = {
  id: "turn-1",
  session_id: "session-1",
  project_id: null,
  workspace_id: "workspace-1",
  user_id: "user-1",
  input_text: "Run checks",
  input_parts: null,
  status: "failed",
  model_selection: null,
  model_profile_snapshot: null,
  final_text: null,
  token_usage: null,
  termination_reason: null,
  loop_state: null,
  iteration_count: 1,
  budget_snapshot: null,
  interrupt_requested_at: null,
  error_code: null,
  error_message: "Tests failed",
  created_at: "2026-06-10T00:00:00Z",
  updated_at: "2026-06-10T00:00:00Z",
}

describe("AgentTodoDock", () => {
  it("renders as an expandable main-panel dock", () => {
    render(<AgentTodoDock items={items} />)

    expect(screen.getByTestId("agent-todo-dock")).toBeInTheDocument()
    expect(screen.getByText("Tasks")).toBeInTheDocument()
    expect(screen.getByText("Editing")).toBeInTheDocument()
    expect(screen.getByTestId("todo-spinner")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Collapse task dock" }))

    expect(screen.getByRole("button", { name: "Expand task dock" })).toBeInTheDocument()
    expect(screen.queryByTestId("todo-checklist")).not.toBeInTheDocument()
    expect(screen.getByText("Editing")).toBeInTheDocument()
  })

  it("marks pending tasks failed after a failed owning turn", () => {
    const projected = deriveTodoDisplayItems(
      [{ content: "Run validation", status: "pending" }],
      failedTurn,
    )

    expect(projected[0]?.displayStatus).toBe("failed")
    render(<AgentTodoDock items={projected} />)

    expect(screen.getByText("Run validation")).toBeInTheDocument()
    expect(screen.getByText("Tests failed")).toBeInTheDocument()
    expect(screen.queryByTestId("todo-spinner")).not.toBeInTheDocument()
  })
})
