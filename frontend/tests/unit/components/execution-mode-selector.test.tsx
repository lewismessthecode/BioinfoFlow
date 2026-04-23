import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toastErrorMock = vi.hoisted(() => vi.fn())

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      askShort: "Ask",
      approveAllShort: "Approve all",
      bypassShort: "Bypass",
      triggerAriaLabel: "Execution mode",
      menuLabel: "Execution mode",
      askTitle: "Ask before risky tools",
      askDescription: "Require approval for risky actions.",
      approveAllTitle: "Approve risky and low-risk tools",
      approveAllDescription: "Require approval more often.",
      bypassTitle: "Bypass approvals",
      bypassDescription: "Run tools without prompts.",
      changeFailed: "Couldn't change mode",
    }
    return labels[key] ?? key
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
  }: {
    children: React.ReactNode
    onClick?: () => void
  }) => (
    <button type="button" onClick={onClick}>
      {children}
    </button>
  ),
}))

import { ExecutionModeSelector } from "@/components/bioinfoflow/chat/execution-mode-selector"

describe("ExecutionModeSelector", () => {
  beforeEach(() => {
    toastErrorMock.mockReset()
  })

  it("falls back to the default ask mode when the conversation has no explicit policy yet", () => {
    render(<ExecutionModeSelector value={null} onChange={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Execution mode" })).toHaveTextContent("Ask")
  })

  it("does not call onChange when the user re-selects the active mode", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(<ExecutionModeSelector value="approve_all" onChange={onChange} />)

    await user.click(screen.getByText("Approve risky and low-risk tools"))

    expect(onChange).not.toHaveBeenCalled()
  })

  it("persists a mode change and surfaces backend failures without hiding the new path", async () => {
    const user = userEvent.setup()
    const onChange = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("boom"))

    render(<ExecutionModeSelector value="auto" onChange={onChange} />)

    await user.click(screen.getByText("Bypass approvals"))
    expect(onChange).toHaveBeenCalledWith("bypass")

    await user.click(screen.getByText("Approve risky and low-risk tools"))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith("Couldn't change mode")
    })
  })
})
