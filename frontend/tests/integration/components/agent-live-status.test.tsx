import { act, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AgentLiveStatus } from "@/components/bioinfoflow/agent/agent-live-status"
import { renderWithProviders } from "@/tests/test-utils"

const reducedMotionState = vi.hoisted(() => ({ value: false }))

vi.mock("@/lib/celebrations", () => ({
  useReducedMotionPreference: () => reducedMotionState.value,
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      "spinner.announcement": "Agent is working",
      "spinner.tracing_clues": "Tracing clues…",
      "spinner.diving_deeper": "Diving deeper…",
      "spinner.connecting_context": "Connecting context…",
      "spinner.checking_details": "Checking details…",
      "spinner.following_evidence": "Following the evidence…",
      "spinner.untangling_problem": "Untangling the problem…",
      "spinner.fitting_pieces": "Fitting the pieces together…",
      "spinner.moving_forward": "Moving things forward…",
    }
    return copy[key] ?? key
  },
}))

describe("AgentLiveStatus", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    reducedMotionState.value = false
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("rotates localized spinner verbs while keeping one stable announcement", () => {
    renderWithProviders(<AgentLiveStatus />)

    const status = screen.getByRole("status")
    expect(status).toHaveTextContent("Agent is working")
    expect(screen.getByTestId("agent-spinner-verb")).toHaveTextContent(
      "Tracing clues…",
    )
    expect(screen.getByTestId("agent-spinner-verb")).toHaveAttribute(
      "aria-hidden",
      "true",
    )

    act(() => vi.advanceTimersByTime(3200))

    expect(screen.getByTestId("agent-spinner-verb")).toHaveTextContent(
      "Diving deeper…",
    )
    expect(status).toHaveTextContent("Agent is working")
  })

  it("keeps the first verb fixed when reduced motion is preferred", () => {
    reducedMotionState.value = true
    renderWithProviders(<AgentLiveStatus />)

    act(() => vi.advanceTimersByTime(12_800))

    expect(screen.getByTestId("agent-spinner-verb")).toHaveTextContent(
      "Tracing clues…",
    )
    expect(vi.getTimerCount()).toBe(0)
  })
})
