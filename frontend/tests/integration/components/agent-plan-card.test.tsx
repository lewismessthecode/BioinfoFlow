import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentPlanCard } from "@/components/bioinfoflow/agent/plan-entry"
import type { ConversationPlan } from "@/lib/agent/conversation-model/types"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: () =>
    (key: string, values?: Record<string, string | number>) => {
      if (key === "plan.step_progress") {
        return `Step ${values?.step} of ${values?.total}`
      }
      if (key === "plan.progress") {
        return `${values?.completed}/${values?.total} complete`
      }
      const copy: Record<string, string> = {
        "plan.expand": "Expand plan",
        "plan.title": "Plan",
      }
      return copy[key] ?? key
    },
}))

function plan(overrides: Partial<ConversationPlan> = {}): ConversationPlan {
  return {
    id: "plan-entry-1",
    runId: "run-1",
    planId: "plan-1",
    revision: 1,
    title: "Investigate",
    active: true,
    items: [
      { id: "step-1", text: "Inspect logs", status: "completed" },
      { id: "step-2", text: "Verify outputs", status: "in_progress" },
    ],
    updatedAt: "2026-08-19T08:00:00.000Z",
    ...overrides,
  }
}

describe("AgentPlanCard", () => {
  it("stops animating when the Run is terminal", () => {
    const view = renderWithProviders(<AgentPlanCard plan={plan()} />)

    expect(screen.getByTestId("agent-plan-trigger").querySelector(".animate-spin"))
      .not.toBeNull()

    view.rerender(<AgentPlanCard plan={plan({ active: false })} />)

    expect(screen.getByTestId("agent-plan-trigger").querySelector(".animate-spin"))
      .toBeNull()
  })

  it("updates the open plan when a newer revision arrives", async () => {
    const user = userEvent.setup()
    const view = renderWithProviders(<AgentPlanCard plan={plan()} />)

    await user.click(screen.getByTestId("agent-plan-trigger"))
    expect(screen.getByText("Verify outputs")).toBeInTheDocument()

    view.rerender(
      <AgentPlanCard
        plan={plan({
          revision: 2,
          items: [
            { id: "step-1", text: "Inspect logs", status: "completed" },
            { id: "step-2", text: "Verify outputs", status: "completed" },
            { id: "step-3", text: "Write report", status: "in_progress" },
          ],
        })}
      />,
    )

    expect(screen.getByText("Write report")).toBeInTheDocument()
    expect(screen.getByTestId("agent-plan-trigger")).toHaveTextContent("Step 3 of 3")
  })
})
