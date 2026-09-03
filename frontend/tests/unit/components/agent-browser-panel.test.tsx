import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      label: "Built-in browser",
      title: "Browser",
      address: "Browser address",
      placeholder: "Enter a URL",
      back: "Back",
      forward: "Forward",
      reload: "Reload",
      go: "Open address",
      openExternal: "Open in a new tab",
      empty: "Enter a URL",
    }
    return copy[key] ?? key
  },
}))

import {
  AgentBrowserPanel,
  resolveEmbeddedBrowserUrl,
} from "@/components/bioinfoflow/agent-browser-panel"

describe("AgentBrowserPanel", () => {
  it("normalizes hostnames and rejects unsafe protocols", () => {
    expect(resolveEmbeddedBrowserUrl("example.com", "http://localhost")).toBe("https://example.com/")
    expect(resolveEmbeddedBrowserUrl("example.com:8080", "http://localhost")).toBe(
      "https://example.com:8080/",
    )
    expect(resolveEmbeddedBrowserUrl("example.com?x=1", "http://localhost")).toBe(
      "https://example.com/?x=1",
    )
    expect(resolveEmbeddedBrowserUrl("example.com#section", "http://localhost")).toBe(
      "https://example.com/#section",
    )
    expect(resolveEmbeddedBrowserUrl("/runs/1", "http://localhost:3000")).toBe(
      "http://localhost:3000/runs/1",
    )
    expect(resolveEmbeddedBrowserUrl("javascript:alert(1)", "http://localhost")).toBe("")
    expect(resolveEmbeddedBrowserUrl("not a url", "http://localhost")).toBe("")
  })

  it("navigates inside a sandboxed iframe", async () => {
    render(<AgentBrowserPanel />)

    await userEvent.type(screen.getByRole("textbox", { name: "Browser address" }), "example.com")
    await userEvent.click(screen.getByRole("button", { name: "Open address" }))

    expect(screen.getByTitle("Browser")).toHaveAttribute("src", "https://example.com/")
    expect(screen.getByTitle("Browser")).toHaveAttribute(
      "sandbox",
      "allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts",
    )
  })
})
