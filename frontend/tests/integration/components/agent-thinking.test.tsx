import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import type { ReasoningTranscriptBlock } from "@/lib/agent/conversation-model/types"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const copy: Record<string, string> = {
      title: "Thinking",
      running: "Thinking…",
      show: "Show thinking",
      hide: "Hide thinking",
    }
    if (key === "duration") return `${values?.seconds ?? "0"}s`
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
    const completed = {
      ...reasoning(
        "thinking-complete",
        "Inspect the workflow first.\nThen validate the parameters.",
        false,
      ),
      durationMs: 1200,
    }
    renderWithProviders(
      <AgentThinking reasoning={completed} />,
    )

    expect(screen.getByText("Inspect the workflow first.")).toBeInTheDocument()
    const disclosure = screen.getByRole("button", { name: /Show thinking/i })
    expect(disclosure).toHaveClass(
      "h-9",
      "hover:bg-muted/25",
      "focus-visible:ring-2",
    )
    expect(screen.getByTestId("agent-thinking-separator")).toHaveTextContent("·")
    expect(screen.getByTestId("agent-thinking-duration")).toHaveTextContent("1.2s")
    expect(screen.getByTestId("agent-thinking")).not.toHaveTextContent(
      "Then validate the parameters.",
    )

    await user.click(disclosure)

    const thinking = screen.getByTestId("agent-thinking")
    expect(thinking).toHaveTextContent(
      "Then validate the parameters.",
    )
    expect(thinking.querySelector(`#${disclosure.getAttribute("aria-controls")}`)).toHaveClass(
      "text-sm",
      "leading-6",
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
