import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
import { ResizeHandle } from "@/components/ui/resize-handle"

describe("ResizeHandle", () => {
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
})
