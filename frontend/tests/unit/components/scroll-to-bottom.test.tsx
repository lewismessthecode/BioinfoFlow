import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ScrollToBottom } from "@/components/bioinfoflow/chat/scroll-to-bottom"

describe("ScrollToBottom", () => {
  it("does not render an unread count badge", () => {
    const { container } = render(<ScrollToBottom visible onClick={() => {}} />)

    expect(screen.getByRole("button", { name: /scroll to bottom/i })).toBeInTheDocument()
    expect(container.textContent).not.toContain("3")
  })
})
