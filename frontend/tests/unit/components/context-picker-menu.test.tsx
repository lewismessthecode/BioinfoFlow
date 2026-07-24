import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ContextPickerMenu } from "@/components/bioinfoflow/agent-runtime/context-picker-menu"

const result = {
  id: "file:src/main.py",
  kind: "file" as const,
  label: "main.py",
  detail: "src/main.py",
  input_part: { type: "file_ref" as const, path: "src/main.py" },
}

describe("ContextPickerMenu", () => {
  it("renders loading, empty, and error states", () => {
    const { rerender } = render(
      <ContextPickerMenu open status="loading" results={[]} onSelect={vi.fn()} />,
    )
    expect(screen.getByText("Searching context…")).toBeInTheDocument()

    rerender(<ContextPickerMenu open status="empty" results={[]} onSelect={vi.fn()} />)
    expect(screen.getByText("No matching context")).toBeInTheDocument()

    rerender(
      <ContextPickerMenu
        open
        status="error"
        error="Search failed"
        results={[]}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText("Search failed")).toBeInTheDocument()
  })

  it("supports pointer and keyboard selection", () => {
    const onSelect = vi.fn()
    const { rerender } = render(
      <ContextPickerMenu
        open
        status="ready"
        results={[result]}
        highlightedIndex={0}
        onSelect={onSelect}
      />,
    )
    fireEvent.mouseDown(screen.getByRole("option", { name: /main.py/ }))
    expect(onSelect).toHaveBeenCalledWith(result)

    rerender(
      <ContextPickerMenu
        open={false}
        status="ready"
        results={[result]}
        onSelect={onSelect}
      />,
    )
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument()
  })
})
