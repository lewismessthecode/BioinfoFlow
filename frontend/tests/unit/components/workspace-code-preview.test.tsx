import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { WorkspaceCodePreview } from "@/components/bioinfoflow/workspace-code-preview"

describe("WorkspaceCodePreview", () => {
  it("uses the real Shiki grammar to highlight WDL keywords", async () => {
    const { rerender } = render(
      <WorkspaceCodePreview content={'{"status":"ready"}'} path="status.json" />,
    )
    const preview = screen.getByTestId("workspace-code-preview")

    await waitFor(() => {
      expect(preview.querySelector(".shiki")).not.toBeNull()
    })

    rerender(
      <WorkspaceCodePreview
        content={[
          "version 1.1",
          "workflow align_reads {",
          "  call bwa_mem",
          "}",
        ].join("\n")}
        path="workflows/align_reads.wdl"
      />,
    )

    await waitFor(() => {
      expect(preview.querySelector(".shiki")).toHaveTextContent(
        "workflow align_reads",
      )
    })

    const workflowToken = Array.from(
      preview.querySelectorAll(".shiki span"),
    ).find((token) => token.textContent === "workflow")
    const callToken = Array.from(preview.querySelectorAll(".shiki span")).find(
      (token) => token.textContent?.trim() === "call",
    )

    expect(workflowToken).toHaveAttribute(
      "style",
      "color:#D73A49;--shiki-dark:#F97583",
    )
    expect(callToken).toHaveAttribute(
      "style",
      "color:#D73A49;--shiki-dark:#F97583",
    )
  })
})
