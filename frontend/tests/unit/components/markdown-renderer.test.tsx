import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
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

  it("renders fenced code blocks with the declared language metadata", () => {
    render(
      <MarkdownRenderer content={"```python\nprint('hello')\n```"} />
    )

    expect(screen.getByText("python")).toBeInTheDocument()
    expect(screen.getByText("print('hello')")).toBeInTheDocument()
  })
})
