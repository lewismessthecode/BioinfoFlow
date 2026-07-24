import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useRef, useState } from "react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: { name?: string }) =>
    ({
      delete: `Delete ${values?.name ?? ""}`,
      deleteAction: "Delete",
      imagePreview: "Image attachment preview",
    })[key] ?? key,
}))

import { AttachmentPreviewDialog } from "@/components/bioinfoflow/agent-runtime/attachment-preview-dialog"

const attachment = {
  id: "image-1",
  filename: "clipboard.png",
  kind: "image" as const,
  status: "ready" as const,
  previewUrl: "/preview/image-1",
}

describe("AttachmentPreviewDialog", () => {
  it("closes with its button and Escape", async () => {
    function Harness() {
      const [open, setOpen] = useState(false)
      const triggerRef = useRef<HTMLButtonElement | null>(null)
      return (
        <>
          <button ref={triggerRef} type="button" onClick={() => setOpen(true)}>
            Preview trigger
          </button>
          <AttachmentPreviewDialog
            open={open}
            attachment={attachment}
            onOpenChange={setOpen}
            returnFocusRef={triggerRef}
          />
        </>
      )
    }
    render(<Harness />)
    fireEvent.click(screen.getByRole("button", { name: "Preview trigger" }))
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    fireEvent.keyDown(document, { key: "Escape" })
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Preview trigger" })).toHaveFocus(),
    )
  })

  it("deletes pending images but hides delete for sent images", () => {
    const onDelete = vi.fn()
    const { rerender } = render(
      <AttachmentPreviewDialog
        open
        attachment={attachment}
        onOpenChange={vi.fn()}
        onDelete={onDelete}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: "Delete clipboard.png" }))
    expect(onDelete).toHaveBeenCalledWith(attachment)

    rerender(
      <AttachmentPreviewDialog
        open
        attachment={attachment}
        onOpenChange={vi.fn()}
        readOnly
      />,
    )
    expect(screen.queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument()
  })
})
