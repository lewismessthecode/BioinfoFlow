import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentHistoryEntries } from "@/components/bioinfoflow/agent/conversation-entries"
import type { HistoryEntry, RunView } from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentActivity.details.show": "Show details",
        "agentActivity.details.hide": "Hide details",
        "agentActivity.details.arguments": "Arguments",
        "agentActivity.details.input": "Input",
        "agentActivity.details.output": "Output",
        "agentActivity.details.error": "Error",
        "agentActivity.status.pending": "Pending",
        "agentActivity.status.running": "Running",
        "agentActivity.status.completed": "Completed",
        "agentActivity.status.failed": "Failed",
        "agentActivity.status.blocked": "Blocked",
        "agentActivity.status.cancelled": "Cancelled",
        "agentActivity.status.interaction_required": "Needs approval",
        "agentActivity.group.parallel": `${values?.count ?? 0} tools running in parallel`,
        "agentActivity.group.serial": `${values?.count ?? 0} tools running in sequence`,
        "agentActivity.group.mixed": `${values?.count ?? 0} tool activities`,
        "agentHistory.reasoning.title": "Thinking summary",
        "agentHistory.reference.attachment": "Attachment",
        "agentHistory.reference.file": "File",
        "agentHistory.reference.directory": "Directory",
        "agentHistory.reference.workflow": "Workflow",
        "agentHistory.reference.run": "Run",
        "agentHistory.reference.openRun": `View run progress for ${values?.name ?? ""}`,
        "agentHistory.reference.artifact": "Artifact",
        "agentHistory.unknown.title": "Unsupported content",
        "agentHistory.plan.title": "Plan",
        "agentHistory.plan.status.pending": "Pending",
        "agentHistory.plan.status.in_progress": "In progress",
        "agentHistory.plan.status.completed": "Completed",
        "agentHistory.plan.progress": `${values?.completed ?? 0}/${values?.total ?? 0} complete`,
        "agentHistory.notice.title": "Agent notice",
        "agentRun.status.completed": "Completed",
        "agentRun.status.failed": "Failed",
        "agentRun.status.cancelled": "Cancelled",
        "agentTranscript.run_ended": `Ended ${values?.time ?? ""}`,
        "agentTranscript.run_duration": `${values?.duration ?? ""}`,
        "agentInteraction.ask_user.title": "The agent asked for input",
        "agentInteraction.ask_user.submit": "Submit answers",
        "agentInteraction.ask_user.recommended": "Recommended",
        "agentInteraction.approval.title": "Approval requested",
        "agentInteraction.approval.approve": "Approve",
        "agentInteraction.approval.reject": "Reject",
        "agentInteraction.approval.input": "Command preview",
        "agentInteraction.approval.effects": "Effects",
        "agentInteraction.approval.reasons": "Reasons",
        "agentInteraction.approval.resources": "Affected resources",
        "agentInteraction.recovery.title": "Recovery requested",
        "agentInteraction.recovery.inspect": "Inspect",
        "agentInteraction.recovery.retry": "Retry",
        "agentInteraction.recovery.cancel": "Cancel",
        "agentInteraction.recovery.selected": "Selected action",
        "agentInteraction.status.pending": "Waiting for response",
        "agentInteraction.status.approved": "Approved",
        "agentInteraction.status.rejected": "Rejected",
        "agentInteraction.status.answered": "Answered",
        "agentInteraction.status.resolved": "Resolved",
        "agentInteraction.submitting": "Submitting…",
        "agentInteraction.submit_failed": "Could not submit. Try again.",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const baseEntry = {
  session_id: "session-1",
  run_id: "run-1",
  schema_version: 1,
  created_at: "2026-08-15T08:00:00Z",
}

describe("AgentHistoryEntries", () => {
  it("renders a failed Run outcome even when no assistant entry exists", () => {
    const failedRun: RunView = {
      id: "run-1",
      session_id: "session-1",
      status: "failed",
      phase: null,
      revision: 4,
      started_at: "2026-08-15T08:00:00.000Z",
      completed_at: "2026-08-15T08:00:02.500Z",
      termination_reason: "agent_failed",
      error: {
        code: "agent_failed",
        message: "The Agent run failed.",
      },
      created_at: "2026-08-15T08:00:00.000Z",
      updated_at: "2026-08-15T08:00:02.500Z",
    }
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "user-only",
        sequence: 1,
        type: "message",
        payload: {
          role: "user",
          parts: [{ id: "text-1", type: "text", text: "Inspect this workflow." }],
        },
      },
    ]

    renderWithProviders(
      <AgentHistoryEntries entries={entries} runs={[failedRun]} />,
    )

    const outcome = screen.getByTestId("agent-run-outcome")
    expect(outcome).toHaveTextContent("Failed")
    expect(outcome).toHaveTextContent("The Agent run failed.")
    expect(outcome).toHaveTextContent("agent_failed")
    expect(outcome).toHaveTextContent(/Ended/)
    expect(outcome).toHaveTextContent("2.5 s")
  })

  it("labels completed and cancelled Run outcomes independently", () => {
    const baseRun: RunView = {
      id: "completed-run",
      session_id: "session-1",
      status: "completed",
      phase: null,
      revision: 3,
      started_at: "2026-08-15T08:00:00.000Z",
      completed_at: "2026-08-15T08:00:01.000Z",
      termination_reason: "completed",
      error: null,
      created_at: "2026-08-15T08:00:00.000Z",
      updated_at: "2026-08-15T08:00:01.000Z",
    }
    const cancelledRun: RunView = {
      ...baseRun,
      id: "cancelled-run",
      status: "cancelled",
      termination_reason: "user_cancelled",
      completed_at: "2026-08-15T08:00:02.000Z",
      updated_at: "2026-08-15T08:00:02.000Z",
    }

    renderWithProviders(
      <AgentHistoryEntries entries={[]} runs={[baseRun, cancelledRun]} />,
    )

    const outcomes = screen.getAllByTestId("agent-run-outcome")
    expect(outcomes).toHaveLength(2)
    expect(outcomes[0]).toHaveTextContent("Completed")
    expect(outcomes[1]).toHaveTextContent("Cancelled")
    expect(outcomes[0]).not.toHaveTextContent("Failed")
    expect(outcomes[1]).not.toHaveTextContent("Failed")
  })

  it("renders typed assistant content and groups tool calls with their durable results", async () => {
    const user = userEvent.setup()
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "assistant-1",
        sequence: 1,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "reasoning-1",
              type: "reasoning_summary",
              text: "I should inspect both files before answering.",
            },
            {
              id: "text-1",
              type: "text",
              text: "## Checked files\n\nI inspected the workflow inputs.",
            },
            {
              id: "call-part-1",
              type: "tool_call",
              call_id: "call-1",
              group_id: "group-1",
              execution_mode: "parallel",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read workflow.nf",
              arguments: { path: "workflow.nf" },
              public_details: [
                {
                  id: "path-1",
                  kind: "path",
                  label: "Path",
                  value: "workflow.nf",
                  format: "path",
                  copyable: false,
                  truncated: false,
                  redacted: false,
                },
              ],
            },
            {
              id: "call-part-2",
              type: "tool_call",
              call_id: "call-2",
              group_id: "group-1",
              execution_mode: "parallel",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read params.json",
              arguments: { path: "params.json" },
              public_details: [
                {
                  id: "path-2",
                  kind: "path",
                  label: "Path",
                  value: "params.json",
                  format: "path",
                  copyable: false,
                  truncated: false,
                  redacted: false,
                },
              ],
            },
          ],
        },
      },
      {
        ...baseEntry,
        id: "tool-result-entry-1",
        sequence: 2,
        type: "message",
        payload: {
          role: "tool",
          parts: [
            {
              id: "result-part-1",
              type: "tool_result",
              call_id: "call-1",
              status: "completed",
              summary: "Read 42 lines",
              output: {
                type: "json",
                value: { provider_private: "must not render" },
              },
              started_at: "2026-08-15T08:00:01Z",
              completed_at: "2026-08-15T08:00:02Z",
              error: null,
            },
          ],
        },
      },
      {
        ...baseEntry,
        id: "tool-result-entry-2",
        sequence: 3,
        type: "message",
        payload: {
          role: "tool",
          parts: [
            {
              id: "result-part-2",
              type: "tool_result",
              call_id: "call-2",
              status: "completed",
              summary: null,
              output: { type: "text", text: "Read 18 lines" },
              started_at: "2026-08-15T08:00:01Z",
              completed_at: "2026-08-15T08:00:02Z",
              error: null,
              public_details: [
                {
                  id: "output-2",
                  kind: "output",
                  label: "Output",
                  value: "Read 18 lines",
                  format: "text",
                  copyable: false,
                  truncated: false,
                  redacted: false,
                },
              ],
            },
          ],
        },
      },
    ]

    renderWithProviders(<AgentHistoryEntries entries={entries} />)

    expect(screen.getByRole("heading", { name: "Checked files" })).toBeInTheDocument()
    expect(screen.getByText("Thinking summary")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /2 tools running in parallel/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    )

    await user.click(screen.getByRole("button", { name: /2 tools running in parallel/i }))

    expect(screen.getByText("Read workflow.nf")).toBeInTheDocument()
    expect(screen.getByText("Read params.json")).toBeInTheDocument()
    expect(screen.getByTestId("agent-history-entries")).not.toHaveTextContent(
      /provider_private|must not render/,
    )

    await user.click(screen.getAllByRole("button", { name: /Show details/i })[1])
    expect(screen.getByText("Read 18 lines")).toBeInTheDocument()
  })

  it("labels historical activity as mixed when grouped tools use different execution modes", () => {
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "assistant-mixed-tools",
        sequence: 1,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "serial-call",
              type: "tool_call",
              call_id: "call-serial",
              group_id: "mixed-group",
              execution_mode: "serial",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read the workflow",
              arguments: { path: "workflow.nf" },
            },
            {
              id: "parallel-call",
              type: "tool_call",
              call_id: "call-parallel",
              group_id: "mixed-group",
              execution_mode: "parallel",
              name: "search",
              display_name: "Search",
              category: "search",
              summary: "Search related inputs",
              arguments: { query: "samples" },
            },
          ],
        },
      },
    ]

    renderWithProviders(<AgentHistoryEntries entries={entries} />)

    expect(
      screen.getByRole("button", { name: "2 tool activities" }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /running in sequence/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /running in parallel/i }),
    ).not.toBeInTheDocument()
  })

  it("shows only the latest revision of each durable plan", () => {
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "plan-1",
        sequence: 1,
        type: "plan",
        payload: {
          plan_id: "analysis-plan",
          revision: 1,
          title: "Analysis plan",
          items: [{ id: "inspect", text: "Inspect old inputs", status: "in_progress" }],
          updated_at: "2026-08-15T08:00:01Z",
        },
      },
      {
        ...baseEntry,
        id: "plan-2",
        sequence: 2,
        type: "plan",
        payload: {
          plan_id: "analysis-plan",
          revision: 2,
          title: "Analysis plan",
          items: [
            { id: "inspect", text: "Inspect current inputs", status: "completed" },
            { id: "run", text: "Run the workflow", status: "in_progress" },
          ],
          updated_at: "2026-08-15T08:00:02Z",
        },
      },
    ]

    renderWithProviders(<AgentHistoryEntries entries={entries} />)

    expect(screen.queryByText("Inspect old inputs")).not.toBeInTheDocument()
    expect(screen.getByText("Inspect current inputs")).toBeInTheDocument()
    expect(screen.getByText("Run the workflow")).toBeInTheDocument()
    expect(screen.getByText("1/2 complete")).toBeInTheDocument()
    expect(screen.queryByText("v2")).not.toBeInTheDocument()
  })

  it("keeps non-contiguous tool activity in transcript order", () => {
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "assistant-ordered",
        sequence: 1,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "call-part-1",
              type: "tool_call",
              call_id: "call-1",
              group_id: "shared-group",
              execution_mode: "serial",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read first file",
              arguments: { path: "first.txt" },
            },
            {
              id: "middle-text",
              type: "text",
              text: "I found a second file to inspect.",
            },
            {
              id: "call-part-2",
              type: "tool_call",
              call_id: "call-2",
              group_id: "shared-group",
              execution_mode: "serial",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read second file",
              arguments: { path: "second.txt" },
            },
          ],
        },
      },
    ]

    renderWithProviders(<AgentHistoryEntries entries={entries} />)

    const transcript = screen.getByTestId("agent-history-entries").textContent ?? ""
    expect(transcript.indexOf("Read first file")).toBeLessThan(
      transcript.indexOf("I found a second file to inspect."),
    )
    expect(transcript.indexOf("I found a second file to inspect.")).toBeLessThan(
      transcript.indexOf("Read second file"),
    )
  })

  it("renders typed public content parts from tool output", () => {
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "assistant-artifact",
        sequence: 1,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "call-part",
              type: "tool_call",
              call_id: "call-artifact",
              group_id: "artifact-group",
              execution_mode: "serial",
              name: "write_report",
              display_name: "Write report",
              category: "write",
              summary: "Create the QC report",
              arguments: { output: "qc-report.html" },
            },
          ],
        },
      },
      {
        ...baseEntry,
        id: "tool-artifact",
        sequence: 2,
        type: "message",
        payload: {
          role: "tool",
          parts: [
            {
              id: "result-artifact",
              type: "tool_result",
              call_id: "call-artifact",
              status: "completed",
              summary: "Created report",
              output: {
                type: "content_parts",
                parts: [
                  {
                    id: "artifact-ref",
                    type: "artifact_ref",
                    artifact_id: "artifact-1",
                    title: "qc-report.html",
                    media_type: "text/html",
                  },
                ],
              },
              started_at: "2026-08-15T08:00:01Z",
              completed_at: "2026-08-15T08:00:02Z",
              error: null,
            },
          ],
        },
      },
    ]

    renderWithProviders(<AgentHistoryEntries entries={entries} />)

    expect(screen.getByText("qc-report.html")).toBeInTheDocument()
    expect(screen.getByText("Artifact")).toBeInTheDocument()
  })

  it("renders references, unknown parts, notices, and resolved interaction history safely", () => {
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "user-1",
        sequence: 1,
        type: "message",
        payload: {
          role: "user",
          parts: [
            { id: "text-1", type: "text", text: "Use this file." },
            {
              id: "file-1",
              type: "file_ref",
              label: "samples.csv",
              path: "inputs/samples.csv",
            },
            {
              id: "unknown-1",
              type: "unknown",
              original_type: "future_public_part",
              display_text: "A future public content block.",
            },
          ],
        },
      },
      {
        ...baseEntry,
        id: "notice-1",
        sequence: 2,
        type: "notice",
        payload: {
          code: "run_resumed",
          message: "The run resumed after restart.",
          details: { internal_checkpoint: "must not render" },
        },
      },
      {
        ...baseEntry,
        id: "interaction-request-1",
        sequence: 3,
        type: "interaction_request",
        payload: {
          interaction_id: "approval-1",
          request: {
            type: "approval",
            call_id: "call-1",
            tool_name: "bash",
            summary: "Allow the workflow submission?",
            input_preview: "bif runs submit",
            allowed_responses: ["approve", "reject"],
            risk: {
              level: "medium",
              effects: ["Creates a workflow run"],
              reasons: [],
              affected_resources: ["project-1"],
            },
          },
        },
      },
      {
        ...baseEntry,
        id: "interaction-response-1",
        sequence: 4,
        type: "interaction_response",
        payload: {
          interaction_id: "approval-1",
          response: { type: "approval", approved: true },
        },
      },
    ]

    renderWithProviders(<AgentHistoryEntries entries={entries} />)

    expect(screen.getByText("samples.csv")).toBeInTheDocument()
    expect(screen.getByText("Unsupported content")).toBeInTheDocument()
    expect(screen.getByText("A future public content block.")).toBeInTheDocument()
    expect(screen.getByText("The run resumed after restart.")).toBeInTheDocument()
    expect(screen.getByText("Allow the workflow submission?")).toBeInTheDocument()
    expect(screen.getByText("Approved")).toBeInTheDocument()
    expect(screen.getByTestId("agent-history-entries")).not.toHaveTextContent(
      /internal_checkpoint|must not render/,
    )
  })

  it("opens a referenced run in the workspace progress view", async () => {
    const user = userEvent.setup()
    const onOpenRun = vi.fn()
    const entries: HistoryEntry[] = [
      {
        ...baseEntry,
        id: "assistant-run-reference",
        sequence: 1,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "run-reference",
              type: "run_ref",
              run_id: "run-42",
              label: "RNA-seq QC",
            },
          ],
        },
      },
    ]

    renderWithProviders(
      <AgentHistoryEntries entries={entries} onOpenRun={onOpenRun} />,
    )

    await user.click(
      screen.getByRole("button", {
        name: "View run progress for RNA-seq QC",
      }),
    )
    expect(onOpenRun).toHaveBeenCalledWith("run-42")
  })
})
