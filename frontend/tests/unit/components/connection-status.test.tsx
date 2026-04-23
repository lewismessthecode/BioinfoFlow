import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      label: "Connection",
      connecting: "Connecting",
      connected: "Connected",
      reconnecting: "Reconnecting",
      disconnected: "Disconnected",
    }
    return copy[key] ?? key
  },
}))

import { ConnectionStatus } from "@/components/bioinfoflow/connection-status"

describe("ConnectionStatus", () => {
  it("keeps the connected state accessible even when the inline label is hidden", () => {
    render(<ConnectionStatus state="connected" />)

    const button = screen.getByRole("button", { name: "Connection: Connected" })

    expect(button).toBeInTheDocument()
    expect(button).not.toHaveTextContent("Connected")
  })

  it("shows the connecting label and animated warning indicator", () => {
    render(<ConnectionStatus state="connecting" />)

    const button = screen.getByRole("button", { name: "Connection: Connecting" })
    const indicator = button.querySelector("span[aria-hidden='true']")

    expect(button).toHaveTextContent("Connecting")
    expect(indicator).toHaveClass("bg-warning")
    expect(indicator).toHaveClass("animate-pulse")
  })

  it("shows the reconnecting label and animation while reconnecting", () => {
    render(<ConnectionStatus state="reconnecting" />)

    const button = screen.getByRole("button", { name: "Connection: Reconnecting" })
    const indicator = button.querySelector("span[aria-hidden='true']")

    expect(button).toHaveTextContent("Reconnecting")
    expect(indicator).toHaveClass("bg-warning")
    expect(indicator).toHaveClass("animate-pulse")
  })

  it("shows the disconnected label with the muted indicator styling", () => {
    render(<ConnectionStatus state="disconnected" />)

    const button = screen.getByRole("button", { name: "Connection: Disconnected" })
    const indicator = button.querySelector("span[aria-hidden='true']")

    expect(button).toHaveTextContent("Disconnected")
    expect(indicator).toHaveClass("bg-muted-foreground/50")
    expect(indicator).not.toHaveClass("animate-pulse")
  })
})
