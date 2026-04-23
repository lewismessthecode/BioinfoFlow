import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      "stage.validation": "Validation",
      "stage.preparation": "Preparation",
      "stage.execution": "Execution",
      "stage.post": "Post-processing",
    }
    return copy[key] ?? key
  },
}))

import { RunErrorCard } from "@/components/bioinfoflow/run-error-card"

describe("RunErrorCard", () => {
  it("renders nothing when no error is present", () => {
    const { container } = render(<RunErrorCard error={null} />)

    expect(container).toBeEmptyDOMElement()
  })

  it("renders the code, translated stage, message, hint, and custom class", () => {
    render(
      <RunErrorCard
        error={{
          stage: "execution",
          code: "TASK_FAILED",
          message: "The align step exited with code 1.",
          hint: "Open the run logs to inspect stderr.",
        }}
        className="custom-shell"
      />,
    )

    const alert = screen.getByRole("alert")
    expect(alert.className).toContain("custom-shell")
    expect(screen.getByText("TASK_FAILED")).toBeInTheDocument()
    expect(screen.getByText("Execution")).toBeInTheDocument()
    expect(screen.getByText("The align step exited with code 1.")).toBeInTheDocument()
    expect(screen.getByText("Open the run logs to inspect stderr.")).toBeInTheDocument()
  })
})
