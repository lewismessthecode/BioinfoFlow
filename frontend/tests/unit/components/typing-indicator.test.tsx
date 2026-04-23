import { render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const reducedMotionState = vi.hoisted(() => ({
  value: false,
}))

vi.mock("framer-motion", () => ({
  motion: {
    div: ({
      children,
      className,
    }: {
      children: React.ReactNode
      className?: string
    }) => <div className={className}>{children}</div>,
    span: ({ className }: { className?: string }) => (
      <span data-testid="typing-dot" className={className} />
    ),
  },
  useReducedMotion: () => reducedMotionState.value,
}))

import { TypingIndicator } from "@/components/bioinfoflow/chat/typing-indicator"

describe("TypingIndicator", () => {
  beforeEach(() => {
    reducedMotionState.value = false
  })

  it("renders the three-dot typing affordance", () => {
    render(<TypingIndicator />)

    expect(screen.getAllByTestId("typing-dot")).toHaveLength(3)
  })

  it("still renders a stable indicator when reduced motion is preferred", () => {
    reducedMotionState.value = true

    render(<TypingIndicator />)

    expect(screen.getAllByTestId("typing-dot")).toHaveLength(3)
  })
})
