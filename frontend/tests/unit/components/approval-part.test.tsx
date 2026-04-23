import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { ApprovalPart } from "@/components/bioinfoflow/chat/parts/approval-part"
import type { ApprovalPart as ApprovalPartType } from "@/lib/chat-types"

function makePart(overrides: Partial<ApprovalPartType> = {}): ApprovalPartType {
  return {
    type: "approval",
    approvalId: "approval-1",
    toolName: "submit_run",
    toolInput: {
      workflow_name: "nf-core/rnaseq",
      notes:
        "This is a long preview field that should stay readable inside the approval card even when it exceeds the inline preview budget.",
    },
    approvalType: "tool_risk",
    status: "pending",
    createdAt: new Date("2026-04-23T10:00:00Z"),
    ...overrides,
  }
}

describe("ApprovalPart", () => {
  it("shows the risky action context and stays in a resolving state until the parent updates the status", async () => {
    const user = userEvent.setup()
    let resolveRequest: (() => void) | undefined
    const onResolve = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRequest = resolve
        }),
    )

    const { rerender } = render(
      <ApprovalPart part={makePart()} onResolve={onResolve} />,
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.getByText("submit_run")).toBeInTheDocument()
    expect(screen.getByText(/workflow_name/i)).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Approve" }))

    expect(onResolve).toHaveBeenCalledWith("approval-1", "approve")
    expect(screen.getByText("Resolving...")).toBeInTheDocument()

    rerender(
      <ApprovalPart
        part={makePart({ status: "approved" })}
        onResolve={onResolve}
      />,
    )

    resolveRequest?.()
    await waitFor(() => {
      expect(screen.getByText("Approved")).toBeInTheDocument()
    })
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
  })

  it("renders terminal statuses without re-showing approval controls", () => {
    const onResolve = vi.fn()

    const { rerender } = render(
      <ApprovalPart part={makePart({ status: "rejected" })} onResolve={onResolve} />,
    )

    expect(screen.getByText("Rejected")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Deny" })).not.toBeInTheDocument()

    rerender(
      <ApprovalPart part={makePart({ status: "cancelled" })} onResolve={onResolve} />,
    )

    expect(screen.getByText("Cancelled")).toBeInTheDocument()

    fireEvent.keyDown(document, { key: "Escape" })
    expect(onResolve).not.toHaveBeenCalled()
  })
})
