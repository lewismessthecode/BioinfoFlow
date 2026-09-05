import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ResizeHandle } from "@/components/ui/resize-handle"

describe("ResizeHandle", () => {
  afterEach(() => {
    document.body.style.cursor = ""
    document.body.style.userSelect = ""
    vi.restoreAllMocks()
  })

  it("uses the localized label and commits keyboard resizing", () => {
    const onResize = vi.fn()
    const onResizeEnd = vi.fn()

    render(
      <ResizeHandle
        side="right"
        onResize={onResize}
        onResizeEnd={onResizeEnd}
        ariaLabel="调整工作区面板大小"
        valueNow={400}
        valueMin={300}
        valueMax={600}
      />,
    )

    const separator = screen.getByRole("separator", {
      name: "调整工作区面板大小",
    })
    fireEvent.keyDown(separator, { key: "ArrowLeft" })

    expect(onResize).toHaveBeenCalledWith(16)
    expect(onResizeEnd).toHaveBeenCalledOnce()
  })

  it("coalesces pointer movement and locks selection while dragging", () => {
    const onResize = vi.fn()
    const onResizeEnd = vi.fn()
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      callback(0)
      return 1
    })

    render(
      <ResizeHandle
        side="right"
        onResize={onResize}
        onResizeEnd={onResizeEnd}
        ariaLabel="Resize workspace"
      />,
    )

    const handle = screen.getByRole("separator", { name: "Resize workspace" })
    fireEvent.pointerDown(handle, { clientX: 300, pointerId: 7 })

    expect(document.body.style.userSelect).toBe("none")
    expect(document.body.style.cursor).toBe("col-resize")

    fireEvent.pointerMove(document, { clientX: 276, pointerId: 7 })
    expect(onResize).toHaveBeenCalledWith(24)

    fireEvent.pointerUp(document, { clientX: 276, pointerId: 7 })
    expect(onResizeEnd).toHaveBeenCalledTimes(1)
    expect(document.body.style.userSelect).toBe("")
    expect(document.body.style.cursor).toBe("")
  })

  it("supports keyboard resizing with an accelerated step", () => {
    const onResize = vi.fn()
    render(
      <ResizeHandle
        side="top"
        onResize={onResize}
        ariaLabel="Resize terminal"
      />,
    )

    const handle = screen.getByRole("separator", { name: "Resize terminal" })
    fireEvent.keyDown(handle, { key: "ArrowUp" })
    fireEvent.keyDown(handle, { key: "ArrowDown", shiftKey: true })

    expect(onResize).toHaveBeenNthCalledWith(1, 16)
    expect(onResize).toHaveBeenNthCalledWith(2, -40)
  })
})
