import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"

describe("MarkdownRenderer link sanitization", () => {
  it("renders http links normally", () => {
    const { container } = render(
      <MarkdownRenderer content="[Example](https://example.com)" />
    )
    const link = container.querySelector("a")
    expect(link).not.toBeNull()
    expect(link!.getAttribute("href")).toBe("https://example.com")
  })

  it("renders mailto links normally", () => {
    const { container } = render(
      <MarkdownRenderer content="[Email](mailto:test@example.com)" />
    )
    const link = container.querySelector("a")
    expect(link).not.toBeNull()
    expect(link!.getAttribute("href")).toBe("mailto:test@example.com")
  })

  it("strips javascript: protocol from href", () => {
    const { container } = render(
      <MarkdownRenderer content='[XSS](javascript:alert(1))' />
    )
    const link = container.querySelector("a")
    // Link may be rendered without href, or not rendered at all — both are safe
    if (link) {
      const href = link.getAttribute("href")
      expect(href === null || !href.startsWith("javascript")).toBe(true)
    }
  })

  it("strips data: protocol from href", () => {
    const { container } = render(
      <MarkdownRenderer content='[Exfil](data:text/html,<script>alert(1)</script>)' />
    )
    const link = container.querySelector("a")
    if (link) {
      const href = link.getAttribute("href")
      expect(href === null || !href.startsWith("data:")).toBe(true)
    }
  })

  it("strips vbscript: protocol from href", () => {
    const { container } = render(
      <MarkdownRenderer content="[VBS](vbscript:msgbox)" />
    )
    const link = container.querySelector("a")
    if (link) {
      const href = link.getAttribute("href")
      expect(href === null || !href.startsWith("vbscript")).toBe(true)
    }
  })

  it("allows relative paths as safe links", () => {
    const { container } = render(
      <MarkdownRenderer content="[Docs](/docs/readme)" />
    )
    const link = container.querySelector("a")
    expect(link).not.toBeNull()
    expect(link!.getAttribute("href")).toBe("/docs/readme")
  })

  it("does not render source pseudo-links as navigable anchors without a citation renderer", () => {
    const { container } = render(<MarkdownRenderer content="[1](source:1)" />)

    const link = container.querySelector("a")
    expect(link).not.toBeNull()
    expect(link!.getAttribute("href")).toBeNull()
    expect(link).toHaveTextContent("1")
  })

  it("delegates known source pseudo-links to the citation renderer", () => {
    const renderSourceCitation = vi.fn((sourceId, children) => (
      <button type="button" data-testid="source-citation" data-source-id={sourceId}>
        {children}
      </button>
    ))

    render(
      <MarkdownRenderer
        content="[7](source:pubmed-7)"
        renderSourceCitation={renderSourceCitation}
      />,
    )

    expect(screen.getByTestId("source-citation")).toHaveAttribute(
      "data-source-id",
      "pubmed-7",
    )
    expect(screen.getByTestId("source-citation")).toHaveTextContent("7")
  })

  it("does not make source-prefixed javascript payloads navigable", () => {
    const { container } = render(
      <MarkdownRenderer content="[bad](source:javascript:alert(1))" />,
    )

    const link = container.querySelector("a")
    expect(link).not.toBeNull()
    expect(link!.getAttribute("href")).toBeNull()
  })

  it("renders fenced code blocks with the declared language metadata", () => {
    render(
      <MarkdownRenderer content={"```python\nprint('hello')\n```"} />
    )

    expect(screen.getByText("python")).toBeInTheDocument()
    expect(screen.getByText("print('hello')")).toBeInTheDocument()
  })

  it("copies fenced code blocks without the fence or language label", () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })

    render(
      <MarkdownRenderer content={"```bash\nls -lah\n  pwd\n```"} />
    )

    expect(screen.getByTestId("markdown-code-block")).toBeInTheDocument()
    expect(screen.getByText("bash")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Copy code" }))

    expect(writeText).toHaveBeenCalledWith("ls -lah\n  pwd")
  })

  it("allows long inline code paths to wrap inside transcript containers", () => {
    const longPath = `/workspace/${"very-long-directory-name-".repeat(8)}result.json`
    render(<MarkdownRenderer content={`Path: \`${longPath}\``} />)

    expect(screen.getByText(longPath)).toHaveClass(
      "break-all",
      "bg-slate-950",
      "ring-1",
      "ring-inset",
      "ring-slate-700",
      "text-slate-100",
    )
  })

  it("bounds wide code blocks and tables to internal horizontal scrolling", async () => {
    const longPath = "/mnt/nas/bioinfoflow/projects/example/" + "nested/".repeat(20)
    const { container } = render(
      <MarkdownRenderer
        content={[
          "```json",
          JSON.stringify({ path: longPath }),
          "```",
          "",
          "| Column | Value |",
          "| --- | --- |",
          `| path | ${longPath} |`,
        ].join("\n")}
      />,
    )

    const codeBlock = container.querySelector("[data-testid='markdown-code-block']")
    expect(codeBlock?.className).toContain("min-w-0")
    expect(codeBlock?.className).toContain("max-w-full")
    expect(codeBlock?.className).toContain("overflow-hidden")
    expect(codeBlock).toHaveClass("bg-slate-950", "text-slate-100", "border-slate-800")

    const highlightedShell = await waitFor(() => {
      const shell = codeBlock?.querySelector("[data-testid='markdown-highlighted-code']")
      expect(shell).not.toBeNull()
      return shell
    })
    expect(highlightedShell?.className).toContain(
      "[&_.shiki]:![background-color:transparent]",
    )
    expect(highlightedShell?.className).not.toContain("shiki-light")

    const tableScroller = container.querySelector("[data-testid='markdown-table-scroller']")
    expect(tableScroller?.className).toContain("max-w-full")
    expect(tableScroller?.className).toContain("overflow-x-auto")
  })
})
