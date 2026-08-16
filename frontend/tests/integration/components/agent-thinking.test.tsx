import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import type { ReasoningTranscriptBlock } from "@/lib/agent/conversation-model/types"
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

function reasoning(
  id: string,
  text: string,
  streaming: boolean,
): ReasoningTranscriptBlock {
  return {
    type: "reasoning",
    id,
    runId: null,
    createdAt: null,
    text,
    streaming,
    provider: null,
    model: null,
    sourceField: "reasoning_summary",
    truncated: false,
    startedAt: null,
    completedAt: null,
    durationMs: null,
  }
}

describe("AgentThinking", () => {
  it("shows a compact live state when reasoning content has not arrived", () => {
    renderWithProviders(
      <AgentThinking
        reasoning={reasoning("thinking-empty", "", true)}
      />,
    )

    expect(screen.getByRole("status")).toHaveTextContent("Thinking…")
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("keeps completed thinking compact until the whole row is expanded", async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentThinking
        reasoning={reasoning(
          "thinking-complete",
          "Inspect the workflow first.\nThen validate the parameters.",
          false,
        )}
      />,
    )

    expect(screen.getByText("Inspect the workflow first.")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Show thinking/i }),
    ).toHaveClass("min-h-9")
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
        reasoning={reasoning(
          "thinking-stream",
          "Inspect the workflow first.",
          true,
        )}
      />,
    )

    await user.click(screen.getByRole("button", { name: /Show thinking/i }))
    view.rerender(
      <AgentThinking
        reasoning={reasoning(
          "thinking-stream",
          "Inspect the workflow first.\nNow validate the parameters.",
          true,
        )}
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
