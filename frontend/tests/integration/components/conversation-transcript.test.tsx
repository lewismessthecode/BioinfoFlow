import { screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ConversationTranscript } from "@/components/bioinfoflow/agent/conversation-transcript"
import type { ConversationViewModel } from "@/lib/agent/conversation-model/types"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) =>
    (key: string, values?: Record<string, string | number>) => {
      const copy: Record<string, string> = {
        "agentTranscript.title": "Agent transcript",
        "agentHistory.plan.title": "Plan",
        "agentHistory.plan.progress": `${values?.completed ?? 0}/${values?.total ?? 0} complete`,
        "agentHistory.plan.status.pending": "Pending",
        "agentHistory.plan.status.in_progress": "In progress",
        "agentHistory.plan.status.completed": "Completed",
        "agentHistory.unknown.title": "Unsupported content",
      }
      return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
    },
}))

const planView: ConversationViewModel = {
  protocolVersion: 1,
  conversation: {
    id: "session-1",
    title: null,
    status: "active",
    workspaceId: "workspace-1",
    projectId: null,
  },
  composer: {
    placement: "docked",
    canSend: true,
    settings: {
      model: { provider: "openai", model: "gpt-5.6", displayName: "GPT-5.6" },
      permissionMode: "ask_dangerous",
      workspaceAccess: "read_write",
      revision: 1,
      environmentScope: { mode: "auto", environmentIds: [] },
    },
    capabilities: {
      modelSelection: true,
      permissionSelection: true,
      environmentSelection: { auto: true, manualMultiSelect: true },
      planMode: false,
    },
  },
  transcript: [
    {
      type: "plan",
      id: "plan-entry-1",
      runId: "run-1",
      createdAt: "2026-08-16T08:00:00.000Z",
      planId: "plan-1",
      revision: 2,
      title: "Investigate the workflow",
      items: [
        { id: "step-1", text: "Inspect logs", status: "completed" },
        { id: "step-2", text: "Verify outputs", status: "in_progress" },
      ],
      updatedAt: "2026-08-16T08:00:01.000Z",
    },
  ],
  activeWork: null,
}

describe("ConversationTranscript", () => {
  it("renders a stable plan block with the existing Agent plan presentation", () => {
    renderWithProviders(<ConversationTranscript view={planView} />)

    expect(screen.getByText("Investigate the workflow")).toBeInTheDocument()
    expect(screen.getByText("1/2 complete")).toBeInTheDocument()
    expect(screen.getByText("Inspect logs")).toBeInTheDocument()
    expect(screen.getByText("Verify outputs")).toBeInTheDocument()
    expect(screen.queryByTestId("agent-unknown-transcript-block")).toBeNull()
  })
})
