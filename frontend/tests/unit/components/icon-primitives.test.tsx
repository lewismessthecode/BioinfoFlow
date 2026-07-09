import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Search } from "@/lib/icons"
import { Icon, IconButton, IconSurface, iconStrokeWidth } from "@/components/ui/icon"

describe("icon primitives", () => {
  it("renders decorative icons with shared size and stroke tokens", () => {
    const { container } = render(<Icon icon={Search} size="sm" />)
    const icon = container.querySelector("svg")

    expect(icon).toHaveClass("size-3.5")
    expect(icon).toHaveAttribute("aria-hidden", "true")
    expect(icon).toHaveAttribute("stroke-width", String(iconStrokeWidth))
  })

  it("renders accessible icon-only buttons with fixed control sizing", () => {
    render(<IconButton icon={Search} label="Search projects" size="sm" />)

    const button = screen.getByRole("button", { name: "Search projects" })
    expect(button).toHaveClass("size-8")
    expect(button.querySelector("svg")).toHaveClass("size-3.5")
  })

  it("renders non-interactive icon surfaces with shared sizing", () => {
    const { container } = render(<IconSurface icon={Search} size="lg" />)
    const surface = container.querySelector("span")

    expect(surface).toHaveClass("size-10")
    expect(surface?.querySelector("svg")).toHaveClass("size-4")
  })
})
