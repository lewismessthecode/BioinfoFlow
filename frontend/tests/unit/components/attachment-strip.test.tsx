import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: { name?: string }) =>
    ({
      label: "Attachments",
      uploading: "Uploading…",
      removing: "Removing…",
      uploadFailed: "Upload failed",
      preview: `Preview ${values?.name ?? ""}`,
      remove: `Remove ${values?.name ?? ""}`,
      retry: `Retry ${values?.name ?? ""}`,
    })[key] ?? key,
}))

import {
  AttachmentStrip,
  type AgentComposerAttachment,
} from "@/components/bioinfoflow/agent-runtime/attachment-strip"

const image: AgentComposerAttachment = {
  id: "image-1",
  filename: "clipboard.png",
  kind: "image",
  status: "ready",
  previewUrl: "/preview/image-1",
}

describe("AttachmentStrip", () => {
  it("previews and removes ready image attachments", () => {
    const onPreview = vi.fn()
    const onRemove = vi.fn()
    render(
      <AttachmentStrip
        attachments={[image]}
        onPreview={onPreview}
        onRemove={onRemove}
      />,
    )

    expect(screen.getByRole("img", { name: "clipboard.png" })).toHaveAttribute(
      "src",
      "/preview/image-1",
    )
    fireEvent.click(screen.getByRole("button", { name: "Preview clipboard.png" }))
    fireEvent.click(screen.getByRole("button", { name: "Remove clipboard.png" }))
    expect(onPreview).toHaveBeenCalledWith(image)
    expect(onRemove).toHaveBeenCalledWith(image)
  })

  it("renders uploading, error, and retry states", () => {
    const onRetry = vi.fn()
    const failed = {
      ...image,
      id: "image-failed",
      status: "error" as const,
      error: "Upload failed",
    }
    render(
      <AttachmentStrip
        attachments={[
          { ...image, id: "image-uploading", status: "uploading" },
          failed,
        ]}
        onRemove={vi.fn()}
        onRetry={onRetry}
      />,
    )
    expect(screen.getByText("Uploading…")).toBeInTheDocument()
    expect(screen.getByText("Upload failed")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Retry clipboard.png" }))
    expect(onRetry).toHaveBeenCalledWith(failed)
  })
})
