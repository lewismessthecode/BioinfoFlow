import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import type {
  ApprovalRequest,
  AskUserRequest,
  RecoveryRequest,
} from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) =>
    (key: string) => {
      const copy: Record<string, string> = {
        "agentInteraction.status.pending": "Waiting for response",
        "agentInteraction.status.approved": "Approved",
        "agentInteraction.status.rejected": "Rejected",
        "agentInteraction.status.answered": "Answered",
        "agentInteraction.status.resolved": "Resolved",
        "agentInteraction.approval.title": "Approval requested",
        "agentInteraction.approval.announcement": "Approval requested. Waiting for response.",
        "agentInteraction.approval.approve": "Approve",
        "agentInteraction.approval.reject": "Reject",
        "agentInteraction.approval.input": "Command preview",
        "agentInteraction.approval.effects": "Effects",
        "agentInteraction.approval.reasons": "Reasons",
        "agentInteraction.approval.resources": "Affected resources",
        "agentInteraction.ask_user.title": "The agent asked for input",
        "agentInteraction.ask_user.announcement": "The agent asked for input. Waiting for response.",
        "agentInteraction.ask_user.submit": "Submit answers",
        "agentInteraction.ask_user.recommended": "Recommended",
        "agentInteraction.recovery.title": "Recovery requested",
        "agentInteraction.recovery.announcement": "Recovery requested. Waiting for response.",
        "agentInteraction.recovery.inspect": "Inspect",
        "agentInteraction.recovery.retry": "Retry",
        "agentInteraction.recovery.cancel": "Cancel",
        "agentInteraction.recovery.selected": "Selected action",
        "agentInteraction.submitting": "Submitting…",
        "agentInteraction.submit_failed": "Could not submit. Try again.",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const approvalRequest: ApprovalRequest = {
  type: "approval",
  call_id: "call-approval",
  tool_name: "bash",
  summary: "Allow workflow submission?",
  input_preview: "bif runs submit workflow.nf",
  allowed_responses: ["approve", "reject"],
  risk: {
    level: "medium",
    effects: ["Creates a workflow run"],
    reasons: ["The command changes project state"],
    affected_resources: ["project-1"],
  },
}

const askUserRequest: AskUserRequest = {
  type: "ask_user",
  call_id: "call-ask",
  questions: [
    {
      id: "mode",
      header: "Execution mode",
      question: "Which mode should the agent use?",
      multi_select: false,
      options: [
        {
          id: "fast",
          label: "Fast mode",
          description: "Runs the shortest analysis.",
          recommended: false,
        },
        {
          id: "safe",
          label: "Safe mode",
          description: "Runs additional validation.",
          recommended: true,
        },
      ],
    },
    {
      id: "delivery",
      header: "Delivery",
      question: "How should results be delivered?",
      multi_select: true,
      options: [
        {
          id: "email",
          label: "Email",
          description: "Send a completion email.",
          recommended: false,
        },
        {
          id: "artifact",
          label: "Artifact",
          description: "Save a downloadable artifact.",
          recommended: true,
        },
      ],
    },
  ],
}

const recoveryRequest: RecoveryRequest = {
  type: "recovery",
  call_id: "call-recovery",
  tool_name: "bash",
  message: "The previous command may have completed before the connection closed.",
  options: [
    {
      id: "inspect",
      label: "Inspect current state",
      description: "Check whether the command already completed.",
      recommended: true,
    },
    {
      id: "retry",
      label: "Retry command",
      description: "Run the command again.",
      recommended: false,
    },
    {
      id: "cancel",
      label: "Cancel operation",
      description: "Stop without retrying.",
      recommended: false,
    },
  ],
}

describe("AgentInteractionCard", () => {
  it("announces a newly arrived pending interaction without interrupting the user", () => {
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-announcement"
        request={approvalRequest}
        onRespond={vi.fn()}
      />,
    )

    const announcement = screen.getByRole("status")
    expect(announcement).toHaveAttribute("aria-live", "polite")
    expect(announcement).toHaveTextContent(
      "Approval requested. Waiting for response.",
    )
  })

  it("submits approval once and disables both actions while pending", async () => {
    const user = userEvent.setup()
    let resolveSubmission: (() => void) | undefined
    const onRespond = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSubmission = resolve
        }),
    )

    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-approval"
        request={approvalRequest}
        onRespond={onRespond}
      />,
    )

    expect(screen.getByText("Allow workflow submission?")).toBeInTheDocument()
    expect(screen.getByText("bif runs submit workflow.nf")).toBeInTheDocument()

    await user.dblClick(screen.getByRole("button", { name: "Approve" }))

    expect(onRespond).toHaveBeenCalledTimes(1)
    expect(onRespond).toHaveBeenCalledWith({ type: "approval", approved: true })
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled()

    resolveSubmission?.()
    await waitFor(() => expect(onRespond).toHaveBeenCalledTimes(1))
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled()
  })

  it("does not submit twice when the response callback returns synchronously", async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-sync"
        request={approvalRequest}
        onRespond={onRespond}
      />,
    )

    await user.dblClick(screen.getByRole("button", { name: "Approve" }))

    expect(onRespond).toHaveBeenCalledTimes(1)
    expect(screen.getByRole("button", { name: "Submitting…" })).toBeDisabled()
  })

  it("submits an approval rejection", async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-reject"
        request={approvalRequest}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Reject" }))

    expect(onRespond).toHaveBeenCalledWith({ type: "approval", approved: false })
  })

  it("renders only the approval actions allowed by the public protocol", () => {
    const { rerender } = renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-approve-only"
        request={{ ...approvalRequest, allowed_responses: ["approve"] }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled()
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument()

    rerender(
      <AgentInteractionCard
        interactionId="interaction-reject-only"
        request={{ ...approvalRequest, allowed_responses: ["reject"] }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled()
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
  })

  it("disables the allowed approval action when no response handler exists", () => {
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-read-only"
        request={{ ...approvalRequest, allowed_responses: ["reject"] }}
      />,
    )

    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled()
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
  })

  it("shows a public error and allows retry after submission fails", async () => {
    const user = userEvent.setup()
    const onRespond = vi
      .fn()
      .mockRejectedValueOnce(new Error("private transport failure"))
      .mockResolvedValueOnce(undefined)
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-retry-submit"
        request={approvalRequest}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Approve" }))

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not submit. Try again.",
    )
    expect(screen.queryByText("private transport failure")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled()

    await user.click(screen.getByRole("button", { name: "Approve" }))
    expect(onRespond).toHaveBeenCalledTimes(2)
  })

  it("collects single-select and multi-select answers before submission", async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-ask"
        request={askUserRequest}
        onRespond={onRespond}
      />,
    )

    expect(screen.getByRole("button", { name: "Submit answers" })).toBeDisabled()

    await user.click(screen.getByRole("radio", { name: /Safe mode/i }))
    await user.click(screen.getByRole("checkbox", { name: /Email/i }))
    await user.click(screen.getByRole("checkbox", { name: /Artifact/i }))

    await user.click(screen.getByRole("button", { name: "Submit answers" }))

    expect(onRespond).toHaveBeenCalledWith({
      type: "ask_user",
      answers: {
        mode: "safe",
        delivery: ["email", "artifact"],
      },
    })
  })

  it("resets draft answers when the interaction changes", async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    const { rerender } = renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-first"
        request={askUserRequest}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole("radio", { name: /Safe mode/i }))
    await user.click(screen.getByRole("checkbox", { name: /Artifact/i }))
    expect(screen.getByRole("radio", { name: /Safe mode/i })).toBeChecked()

    rerender(
      <AgentInteractionCard
        interactionId="interaction-second"
        request={askUserRequest}
        onRespond={onRespond}
      />,
    )

    expect(screen.getByRole("radio", { name: /Safe mode/i })).not.toBeChecked()
    expect(screen.getByRole("checkbox", { name: /Artifact/i })).not.toBeChecked()
    expect(screen.getByRole("button", { name: "Submit answers" })).toBeDisabled()
  })

  it.each([
    ["Inspect current state", "inspect"],
    ["Retry command", "retry"],
    ["Cancel operation", "cancel"],
  ] as const)("submits recovery choice %s", async (buttonName, choice) => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    renderWithProviders(
      <AgentInteractionCard
        interactionId={`interaction-${choice}`}
        request={recoveryRequest}
        onRespond={onRespond}
      />,
    )

    await user.click(screen.getByRole("button", { name: buttonName }))

    expect(onRespond).toHaveBeenCalledWith({ type: "recovery", choice })
  })

  it("offers only recovery choices supplied by the request", () => {
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-retry-only"
        request={{
          ...recoveryRequest,
          options: recoveryRequest.options.filter((option) => option.id === "retry"),
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByRole("button", { name: "Retry command" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Inspect" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument()
  })

  it("renders completed approval history without active controls", () => {
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-completed"
        request={approvalRequest}
        response={{ type: "approval", approved: true }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByText("Approved")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument()
  })

  it("renders completed ask-user and recovery state as read-only", () => {
    const { rerender } = renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-answered"
        request={askUserRequest}
        response={{
          type: "ask_user",
          answers: { mode: "safe", delivery: ["artifact"] },
        }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByText("Answered")).toBeInTheDocument()
    expect(screen.getByRole("radio", { name: /Safe mode/i })).toBeChecked()
    expect(screen.getByRole("radio", { name: /Safe mode/i })).toBeDisabled()
    expect(screen.queryByRole("button", { name: "Submit answers" })).not.toBeInTheDocument()

    rerender(
      <AgentInteractionCard
        interactionId="interaction-recovered"
        request={recoveryRequest}
        response={{ type: "recovery", choice: "retry" }}
        onRespond={vi.fn()}
      />,
    )

    expect(screen.getByText("Resolved")).toBeInTheDocument()
    expect(screen.getByText("Retry command")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Retry command" })).not.toBeInTheDocument()
  })
})
