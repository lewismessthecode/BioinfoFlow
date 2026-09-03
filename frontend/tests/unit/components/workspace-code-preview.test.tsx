import { render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

const { codeToHtml } = vi.hoisted(() => ({
  codeToHtml: vi.fn(
    async (content: string, options: { lang: string }) =>
      `<pre class="shiki" data-shiki-language="${options.lang}"><code>${content}</code></pre>`,
  ),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    key === "codePreview.wdlFallback"
      ? "WDL syntax highlighting uses Scala fallback"
      : key,
}))
vi.mock("shiki", () => ({ codeToHtml }))

import { WorkspaceCodePreview } from "@/components/bioinfoflow/workspace-code-preview"

describe("WorkspaceCodePreview", () => {
  it("uses an explicit Scala fallback for WDL", async () => {
    render(
      <WorkspaceCodePreview
        path="workflows/main.wdl"
        content="workflow hello {}"
      />,
    )

    const preview = screen.getByTestId("workspace-code-preview")
    expect(preview).toHaveAttribute("data-language", "wdl")
    expect(preview).toHaveAttribute("data-highlight-language", "scala")
    expect(preview).toHaveAccessibleName(
      "WDL syntax highlighting uses Scala fallback",
    )
    await waitFor(() =>
      expect(codeToHtml).toHaveBeenCalledWith(
        "workflow hello {}",
        expect.objectContaining({ lang: "scala" }),
      ),
    )
  })
})
