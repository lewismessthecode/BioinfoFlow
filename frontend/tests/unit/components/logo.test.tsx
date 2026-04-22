import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Logo } from "@/components/bioinfoflow/logo"

describe("Logo", () => {
  it("renders the extracted brand icon asset", () => {
    const { container } = render(<Logo size={48} />)

    const image = container.querySelector("img")
    expect(image).not.toBeNull()
    expect(image?.getAttribute("src")).toContain("/brand-icon.png?v=")
    expect(image?.getAttribute("width")).toBe("48")
    expect(image?.getAttribute("height")).toBe("48")
  })
})
