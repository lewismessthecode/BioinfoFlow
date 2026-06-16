import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AgentTodoDock } from "@/components/bioinfoflow/agent-runtime/agent-todo-dock"
import type { AgentTodoDisplayItem } from "@/lib/agent-runtime"

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

  it("does not spin failed in-progress tasks", () => {
    render(
      <AgentTodoDock
        items={[
          {
            content: "Run validation",
            status: "in_progress",
            activeForm: "Running tests",
            displayStatus: "failed",
            errorMessage: "Tests failed",
          },
        ]}
      />,
    )

    expect(screen.getByText("Run validation")).toBeInTheDocument()
    expect(screen.getByText("Tests failed")).toBeInTheDocument()
    expect(screen.queryByTestId("todo-spinner")).not.toBeInTheDocument()
  })
})
