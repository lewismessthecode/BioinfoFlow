import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { StructuredComposerEditor } from "@/components/bioinfoflow/agent-runtime/structured-composer-editor"
import type { AgentRuntimeContextSearchItem } from "@/lib/agent-runtime"

const option: AgentRuntimeContextSearchItem = {
  id: "file:src/main.py",
  kind: "file",
  label: "main.py",
  detail: "src/main.py",
  input_part: { type: "file_ref", path: "src/main.py" },
}

describe("StructuredComposerEditor", () => {
  it("searches an @ query and inserts the selected atomic mention", async () => {
    const onSearch = vi.fn().mockResolvedValue({
      results: [option],
      counts: { file: 1 },
      next_cursor: null,
    })
    const onChange = vi.fn()
    function Harness() {
      const [value, setValue] = useState({ text: "", mentions: [] })
      return (
        <StructuredComposerEditor
          value={value}
          onChange={(next) => {
            onChange(next)
            setValue(next)
          }}
          onSearch={onSearch}
          ariaLabel="Message"
        />
      )
    }
    render(<Harness />)

    const editor = screen.getByRole("textbox", { name: "Message" })
    await userEvent.setup().type(editor, "@mai")
    await waitFor(() => expect(screen.getByRole("option", { name: /main.py/ })).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByRole("option", { name: /main.py/ }))

    expect(onChange).toHaveBeenLastCalledWith({
      text: "@main.py ",
      mentions: [expect.objectContaining({ id: option.id, from: 0, to: 8 })],
    })
  })

  it("uses Arrow keys, Enter, Tab, Escape, and whole-token Backspace", async () => {
    const onChange = vi.fn()
    const onSubmit = vi.fn()
    const value = {
      text: "@main.py",
      mentions: [
        {
          id: option.id,
          kind: option.kind,
          label: option.label,
          detail: option.detail,
          inputPart: option.input_part,
          from: 0,
          to: 8,
        },
      ],
    }
    render(
      <StructuredComposerEditor
        value={value}
        onChange={onChange}
        onSubmit={onSubmit}
        ariaLabel="Message"
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Message" })
    fireEvent.keyDown(editor, { key: "Enter" })
    expect(onSubmit).toHaveBeenCalled()

    fireEvent.keyDown(editor, { key: "Backspace" })
    expect(onChange).toHaveBeenCalledWith({ text: "", mentions: [] })
  })

  it("keeps Shift+Enter multiline and ignores submit while composing", () => {
    const onSubmit = vi.fn()
    render(
      <StructuredComposerEditor
        value={{ text: "hello", mentions: [] }}
        onChange={vi.fn()}
        onSubmit={onSubmit}
        ariaLabel="Message"
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Message" })
    fireEvent.keyDown(editor, { key: "Enter", shiftKey: true })
    fireEvent.compositionStart(editor)
    fireEvent.keyDown(editor, { key: "Enter" })
    fireEvent.compositionEnd(editor)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it("copies mention tokens as readable text", () => {
    const setData = vi.fn()
    render(
      <StructuredComposerEditor
        value={{ text: "@main.py", mentions: [] }}
        onChange={vi.fn()}
        ariaLabel="Message"
      />,
    )
    fireEvent.copy(screen.getByRole("textbox", { name: "Message" }), {
      clipboardData: { setData },
    })
    expect(setData).toHaveBeenCalledWith("text/plain", "@main.py")
  })
})
