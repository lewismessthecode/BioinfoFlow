import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { WorkspaceCodePreview } from "@/components/bioinfoflow/workspace-code-preview"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}))

describe("WorkspaceCodePreview", () => {
  it("uses the real Shiki grammar to highlight WDL keywords", async () => {
    const { rerender } = render(
      <WorkspaceCodePreview content={'{"status":"ready"}'} path="status.json" />,
    )
    const preview = screen.getByTestId("workspace-code-preview")
    expect(preview).toHaveAttribute(
      "aria-label",
      "codePreview.label",
    )

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

    expect(preview).toHaveAttribute("data-language", "wdl")
    expect(preview).toHaveAttribute("data-highlight-language", "wdl")
    const workflowToken = Array.from(
      preview.querySelectorAll(".shiki span"),
    ).find((token) => token.textContent === "workflow")
    const callToken = Array.from(preview.querySelectorAll(".shiki span")).find(
      (token) => token.textContent?.trim() === "call",
    )

    expect(workflowToken).toHaveAttribute("style")
    expect(callToken).toHaveAttribute("style")
    expect(workflowToken?.getAttribute("style")).toBe(
      callToken?.getAttribute("style"),
    )
  })
})
