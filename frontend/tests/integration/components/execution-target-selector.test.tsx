import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ExecutionTargetSelector } from "@/components/bioinfoflow/agent/execution-target-selector"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => ({
    label: "Execution scope",
    auto: "Auto",
    manual: "Manual",
    localOnly: "Local only",
    active: "Working on {alias}",
  })[key] ?? key,
}))

const targets = [
  { id: "local", handle: "local", alias: "Local", kind: "local" as const, status: "online" as const, primary: true, disabledReason: null },
  { id: "remote-1", handle: "ssh:cluster-a", alias: "Cluster A", kind: "remote_ssh" as const, status: "online" as const, primary: false, disabledReason: null },
]

describe("ExecutionTargetSelector", () => {
  it("switches to manual selection and never removes the last target", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderWithProviders(
      <ExecutionTargetSelector
        targets={targets}
        scope={{ mode: "auto", targetIds: [] }}
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole("button", { name: /Execution scope: Auto/i }))
    await user.click(screen.getByRole("menuitemcheckbox", { name: "Cluster A" }))

    expect(onChange).toHaveBeenCalledWith({ mode: "manual", targetIds: ["remote-1"] })
  })

  it("shows the safe active alias without exposing connection coordinates", () => {
    renderWithProviders(
      <ExecutionTargetSelector
        targets={targets}
        scope={{ mode: "auto", targetIds: [] }}
        activeTarget={targets[1]}
        onChange={vi.fn()}
      />,
    )

    expect(screen.getByText("Cluster A")).toBeInTheDocument()
    expect(screen.queryByText(/@|cluster\.example/)).not.toBeInTheDocument()
  })
})
