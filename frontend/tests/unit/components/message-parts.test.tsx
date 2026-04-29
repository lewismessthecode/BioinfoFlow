import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { TextPart } from "@/components/bioinfoflow/chat/parts/text-part"
import { ThinkingPart } from "@/components/bioinfoflow/chat/parts/thinking-part"
import { ToolCallGroup } from "@/components/bioinfoflow/chat/parts/tool-call-part"

describe("assistant message parts", () => {
  it("renders assistant text as markdown", () => {
    const { container } = render(
      <TextPart
        part={{
          type: "text",
          text: "**Investigating Database Issue**\n\n- permissions\n- config",
        }}
      />
    )

    expect(screen.getByText("Investigating Database Issue", { selector: "strong" })).toBeInTheDocument()
    expect(container.querySelectorAll("li")).toHaveLength(2)
  })

  it("renders expanded thinking content as markdown", () => {
    const { container } = render(
      <ThinkingPart
        part={{
          type: "thinking",
          text: "**Investigating Database Issue**\n\n- permissions\n- config",
          isStreaming: false,
        }}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: /thought for/i }))

    expect(screen.getByText("Investigating Database Issue", { selector: "strong" })).toBeInTheDocument()
    expect(container.querySelectorAll("li")).toHaveLength(2)
  })

  it("renders tool groups as a lightweight disclosure instead of a bordered card", () => {
    const { container } = render(
      <ToolCallGroup
        parts={[
          {
            type: "tool-call",
            id: "tool-1",
            toolName: "shell",
            args: {},
            status: "done",
            durationMs: 383,
          },
          {
            type: "tool-call",
            id: "tool-2",
            toolName: "shell",
            args: {},
            status: "done",
            durationMs: 4300,
          },
        ]}
      />
    )

    const wrapper = container.firstElementChild
    expect(wrapper).not.toHaveClass("rounded-lg")
    expect(wrapper).not.toHaveClass("border")

    expect(screen.queryByText(/^shell$/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /used 2 tools/i }))

    expect(screen.getAllByText(/^shell$/i)).toHaveLength(2)
  })

  it("keeps the latest completed tool group visibly active while the response is still running", () => {
    render(
      <ToolCallGroup
        isActiveFallback
        parts={[
          {
            type: "tool-call",
            id: "tool-1",
            toolName: "list_runs",
            args: {},
            status: "done",
            durationMs: 1,
          },
          {
            type: "tool-call",
            id: "tool-2",
            toolName: "show_run",
            args: {},
            status: "done",
            durationMs: 1,
          },
        ]}
      />
    )

    const button = screen.getByRole("button", { name: /working with tools/i })
    expect(button.querySelector(".animate-spin")).not.toBeNull()
    expect(screen.queryByText(/used 2 tools/i)).not.toBeInTheDocument()
  })
})
