import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      title: "Thinking",
      running: "Thinking…",
      show: "Show thinking",
      hide: "Hide thinking",
    }
    return copy[key] ?? key
  },
}))

describe("AgentThinking", () => {
  it("shows a compact live state when reasoning content has not arrived", () => {
    renderWithProviders(
      <AgentThinking
        active
        part={{
          id: "thinking-empty",
          type: "reasoning_summary",
          text: "",
          end_offset: 0,
        }}
      />,
    )

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…")
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("keeps completed thinking compact until the whole row is expanded", async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentThinking
        part={{
          id: "thinking-complete",
          type: "reasoning_summary",
          text: "Inspect the workflow first.\nThen validate the parameters.",
          end_offset: 57,
        }}
      />,
    )

    expect(screen.getByText("Inspect the workflow first.")).toBeInTheDocument()
    expect(screen.getByTestId("agent-thinking")).not.toHaveTextContent(
      "Then validate the parameters.",
    )

    await user.click(screen.getByRole("button", { name: /Show thinking/i }))

    expect(screen.getByTestId("agent-thinking")).toHaveTextContent(
      "Then validate the parameters.",
    )
  })

  it("preserves expansion while streamed content updates the same part", async () => {
    const user = userEvent.setup()
    const view = renderWithProviders(
      <AgentThinking
        active
        part={{
          id: "thinking-stream",
          type: "reasoning_summary",
          text: "Inspect the workflow first.",
          end_offset: 27,
        }}
      />,
    )

    await user.click(screen.getByRole("button", { name: /Show thinking/i }))
    view.rerender(
      <AgentThinking
        active
        part={{
          id: "thinking-stream",
          type: "reasoning_summary",
          text: "Inspect the workflow first.\nNow validate the parameters.",
          end_offset: 56,
        }}
      />,
    )

    expect(screen.getByTestId("agent-thinking")).toHaveTextContent(
      "Now validate the parameters.",
    )
    expect(screen.getByRole("button", { name: /Hide thinking/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    )
  })
})
