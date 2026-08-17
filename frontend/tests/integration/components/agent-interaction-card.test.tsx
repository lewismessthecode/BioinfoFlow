import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentInteractionCard as StableAgentInteractionCard } from "@/components/bioinfoflow/agent/interaction-card"
import type {
  ConversationInteractionResponse,
  InteractionTranscriptBlock,
} from "@/lib/agent/conversation-model/types"
import type {
  ApprovalRequest,
  AskUserRequest,
  InteractionRequest,
  InteractionResponse,
  RecoveryRequest,
} from "@/lib/agent/contracts"
import { interactionFromLegacy } from "@/lib/agent/projection/legacy-transcript-adapter"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
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
        "agentInteraction.approval.target": "Execution target",
        "agentInteraction.approval.action.command": "Run command",
        "agentInteraction.approval.action.escalation":
          "Allow one-time sandbox escalation",
        "agentInteraction.approval.action.write": "Write file",
        "agentInteraction.approval.action.edit": "Edit file",
        "agentInteraction.approval.action.read": "Read file",
        "agentInteraction.approval.action.tool": `Run ${values?.toolName ?? "tool"}`,
        "agentInteraction.approval.effect.read": "Reads data",
        "agentInteraction.approval.effect.write": "Changes files",
        "agentInteraction.approval.effect.delete": "Deletes data",
        "agentInteraction.approval.effect.network": "Uses the network",
        "agentInteraction.approval.effect.process_control": "Controls processes",
        "agentInteraction.approval.effect.privilege": "Uses elevated access",
        "agentInteraction.approval.effect.execute": "Runs a command",
        "agentInteraction.approval.effects": "Effects",
        "agentInteraction.approval.reasons": "Reasons",
        "agentInteraction.approval.justification":
          `Agent justification: ${values?.justification ?? ""}`,
        "agentInteraction.approval.reason.sandbox_escalation":
          "This exact command will run once with the sandbox filesystem restrictions disabled.",
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
        "agentInteraction.recovery.message.unknown_tool_effect": `BioinfoFlow could not confirm whether ${values?.toolName ?? "the tool"} changed the target. Choose how to continue.`,
        "agentInteraction.recovery.option.inspect.label": "Inspect state",
        "agentInteraction.recovery.option.inspect.description": "Continue without replaying the operation.",
        "agentInteraction.recovery.option.retry.label": "Retry operation",
        "agentInteraction.recovery.option.retry.description": "Explicitly allow the operation to run again.",
        "agentInteraction.recovery.option.cancel.label": "Cancel run",
        "agentInteraction.recovery.option.cancel.description": "Stop without replaying the operation.",
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

function AgentInteractionCard({
  interaction,
  interactionId,
  request,
  response = null,
  actionable,
  expired,
  onRespond,
}: {
  interaction?: InteractionTranscriptBlock
  interactionId?: string
  request?: InteractionRequest
  response?: InteractionResponse | null
  actionable?: boolean
  expired?: boolean
  onRespond?: (
    response: ConversationInteractionResponse,
  ) => void | Promise<void>
}) {
  const stableInteraction =
    interaction ??
    (interactionId && request
      ? interactionFromLegacy(interactionId, request, response)
      : null)
  if (!stableInteraction) return null
  return (
    <StableAgentInteractionCard
      interaction={stableInteraction}
      actionable={actionable}
      expired={expired}
      onRespond={onRespond}
    />
  )
}

describe("AgentInteractionCard", () => {
  it("localizes backend-owned recovery copy from stable codes and choice IDs", () => {
    renderWithProviders(
      <AgentInteractionCard
        interaction={{
          type: "interaction",
          id: "recovery-card",
          runId: "run-1",
          createdAt: null,
          interactionId: "run-1:call-recovery",
          status: "pending",
          request: {
            type: "recovery",
            callId: "call-recovery",
            toolName: "bash",
            messageCode: "unknown_tool_effect",
            messageParams: { tool_name: "bash" },
            messageFallback: "Backend-owned English recovery text",
            options: recoveryRequest.options,
          },
          response: null,
        }}
        actionable
        onRespond={vi.fn()}
      />,
    )

    expect(
      screen.getByText(
        "BioinfoFlow could not confirm whether bash changed the target. Choose how to continue.",
      ),
    ).toBeInTheDocument()
    expect(screen.getAllByText("Inspect state").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Retry operation").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Cancel run").length).toBeGreaterThan(0)
    expect(screen.queryByText("Backend-owned English recovery text")).not.toBeInTheDocument()
    expect(screen.queryByText("Inspect current state")).not.toBeInTheDocument()
  })

  it("renders approval as a theme-safe transcript card", () => {
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-theme"
        request={approvalRequest}
        onRespond={vi.fn()}
      />,
    )

    const card = screen.getByTestId("agent-interaction-card")
    expect(card).toHaveAttribute("data-interaction-type", "approval")
    expect(card).toHaveClass("bg-warning-muted/25")
    const reject = screen.getByRole("button", { name: "Reject" })
    expect(reject).toHaveClass("dark:bg-transparent")
    expect(reject).not.toHaveClass("dark:bg-input/30")
  })

  it("explains the approval action and its user-facing reasons", () => {
    renderWithProviders(
      <AgentInteractionCard
        interaction={{
          type: "interaction",
          id: "approval-details",
          runId: "run-1",
          createdAt: null,
          interactionId: "interaction-details",
          status: "pending",
          request: {
            type: "approval",
            callId: "call-approval",
            toolName: "bash",
            summary: "Run command",
            inputPreview: "touch e2e-approved.txt",
            allowedResponses: ["approve", "reject"],
            risk: {
              level: "act_high",
              effects: ["execute", "write"],
              reasons: ["command semantics classified as act_high"],
              reasonCodes: ["sandbox_escalation"],
              justification: "write the explicitly approved external target",
              affectedResources: ["e2e-approved.txt"],
            },
            target: {
              environmentId: "local",
              displayName: "Local",
              kind: "local",
              host: null,
            },
          },
          response: null,
        }}
        onRespond={vi.fn()}
      />,
    )

    const card = screen.getByTestId("agent-interaction-card")
    expect(
      within(card).getByText("Allow one-time sandbox escalation"),
    ).toBeInTheDocument()
    expect(within(card).getByText("bash")).toBeInTheDocument()
    expect(within(card).getByText("touch e2e-approved.txt")).toBeInTheDocument()
    expect(within(card).getByText("Local")).toBeInTheDocument()
    expect(within(card).getByText("Runs a command")).toBeInTheDocument()
    expect(within(card).getByText("Changes files")).toBeInTheDocument()
    expect(within(card).getByText("e2e-approved.txt")).toBeInTheDocument()
    expect(within(card).queryByText(/act_high/i)).not.toBeInTheDocument()
    expect(
      within(card).getByText(
        "This exact command will run once with the sandbox filesystem restrictions disabled.",
      ),
    ).toBeInTheDocument()
    expect(
      within(card).getByText(
        "Agent justification: write the explicitly approved external target",
      ),
    ).toBeInTheDocument()
  })

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

  it("supports keyboard selection for radio and checkbox answers", async () => {
    const user = userEvent.setup()
    const onRespond = vi.fn()
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-ask-keyboard"
        request={askUserRequest}
        onRespond={onRespond}
      />,
    )

    const fast = screen.getByRole("radio", { name: /Fast mode/i })
    const safe = screen.getByRole("radio", { name: /Safe mode/i })
    const email = screen.getByRole("checkbox", { name: /Email/i })
    const artifact = screen.getByRole("checkbox", { name: /Artifact/i })

    fast.focus()
    await user.keyboard("{ArrowRight}")
    expect(safe).toHaveFocus()
    expect(safe).toBeChecked()

    email.focus()
    await user.keyboard(" ")
    artifact.focus()
    await user.keyboard(" ")
    expect(email).toBeChecked()
    expect(artifact).toBeChecked()
    expect(email.closest("label")).toHaveClass(
      "focus-within:ring-2",
      "focus-within:ring-ring/40",
    )

    await user.click(screen.getByRole("button", { name: "Submit answers" }))
    expect(onRespond).toHaveBeenCalledWith({
      type: "ask_user",
      answers: {
        mode: "safe",
        delivery: ["email", "artifact"],
      },
    })
  })

  it("presents Ask User as one editorial decision surface with numbered option rows", async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-ask-layout"
        request={askUserRequest}
        onRespond={vi.fn()}
      />,
    )

    const card = screen.getByTestId("agent-interaction-card")
    const questions = screen.getAllByTestId("agent-ask-question")
    const firstQuestion = questions[0]
    const optionList = within(firstQuestion).getByTestId("agent-ask-options")
    const optionRows = within(firstQuestion).getAllByTestId("agent-ask-option")

    expect(card).not.toHaveClass("shadow-md", "shadow-lg", "shadow-xl")
    expect(questions).toHaveLength(2)
    expect(firstQuestion).toHaveClass("border-t", "first:border-t-0")
    expect(within(firstQuestion).getByText("Execution mode")).toHaveClass(
      "text-[10px]",
      "uppercase",
      "tracking-[0.12em]",
    )
    expect(
      within(firstQuestion).getByText("Which mode should the agent use?"),
    ).toHaveClass(
      "[overflow-wrap:anywhere]",
      "text-base",
      "font-semibold",
      "tracking-[-0.01em]",
    )
    expect(optionList).toHaveClass("divide-y")
    expect(optionList).not.toHaveClass("grid-cols-2", "sm:grid-cols-2")
    expect(optionRows).toHaveLength(2)
    expect(optionRows[0]).not.toHaveClass("rounded-[8px]", "border")
    expect(within(optionRows[0]).getByText("01")).toHaveAttribute(
      "aria-hidden",
      "true",
    )
    expect(within(optionRows[1]).getByText("02")).toHaveAttribute(
      "aria-hidden",
      "true",
    )
    expect(within(optionRows[0]).getByText("Fast mode")).toHaveClass(
      "text-sm",
      "font-medium",
    )
    expect(
      within(optionRows[0]).getByText("Runs the shortest analysis."),
    ).toHaveClass("text-xs", "leading-5")

    const recommended = within(optionRows[1]).getByText("Recommended")
    expect(recommended).toHaveClass("text-[9px]", "tracking-[0.08em]")

    const safe = within(optionRows[1]).getByRole("radio", {
      name: /Safe mode/i,
    })
    await user.click(safe)
    expect(safe).toBeChecked()
    expect(optionRows[1]).toHaveClass(
      "bg-muted/30",
      "dark:bg-muted/20",
    )
  })

  it("keeps long agent-generated question and option text inside the decision surface", () => {
    const longToken = "UnbrokenAgentIdentifier".repeat(12)
    renderWithProviders(
      <AgentInteractionCard
        interactionId="interaction-ask-long-copy"
        request={{
          ...askUserRequest,
          questions: [
            {
              ...askUserRequest.questions[0],
              header: longToken,
              question: longToken,
              options: [
                {
                  ...askUserRequest.questions[0].options[0],
                  label: longToken,
                  description: longToken,
                },
              ],
            },
          ],
        }}
        onRespond={vi.fn()}
      />,
    )

    const matches = screen.getAllByText(longToken)
    expect(matches).toHaveLength(4)
    for (const text of matches) {
      expect(text).toHaveClass("[overflow-wrap:anywhere]")
    }
    expect(screen.getByTestId("agent-ask-option").lastElementChild).toHaveClass(
      "min-w-0",
      "overflow-hidden",
    )
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
