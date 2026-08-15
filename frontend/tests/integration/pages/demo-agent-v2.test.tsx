import { act, fireEvent, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import DemoPage from "@/app/(demo)/demo/page"
import { DemoReplayProvider } from "@/lib/demo/demo-context"
import type { SessionSnapshot } from "@/lib/agent/contracts"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, string> = {
      "agentTranscript.title": "Conversation",
      "demoAgent.start": "Start Demo",
      "demoAgent.pause": "Pause Demo",
      "demoAgent.restart": "Restart Demo",
      "demoAgent.progress": "Demo progress",
      "demoAgent.status.complete": "Demo complete",
    }
    return copy[`${namespace}.${key}`] ?? `${namespace}.${key}`
  },
}))

vi.mock("@/components/bioinfoflow/dag/dag-panel", () => ({
  DagPanel: () => <div>Pipeline graph</div>,
}))

describe("public agent demo", () => {
  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it("renders the recording through the formal Agent Transcript", async () => {
    vi.useFakeTimers()
    const snapshot: SessionSnapshot = {
      session: {
        id: "session-1",
        user_id: "demo-user",
        workspace_id: "workspace-demo",
        project_id: "project-demo",
        title: "Demo",
        model: {
          provider: "demo",
          model: "demo-model",
          display_name: "Demo Model",
          supports_vision: true,
          supports_reasoning: true,
          supports_tools: true,
        },
        permission_mode: "ask_dangerous",
        workspace_access: "read_write",
        status: "active",
        created_at: "2026-04-24T09:00:00Z",
        updated_at: "2026-04-24T09:00:00Z",
      },
      runs: [],
      entries: [],
      active_run: null,
    }
    const recording = [
      {
        t: 0,
        kind: "agent",
        event: { type: "snapshot", snapshot },
      },
      {
        t: 10,
        kind: "agent",
        event: {
          type: "entry.committed",
          entry: {
            id: "assistant-1",
            session_id: "session-1",
            run_id: null,
            sequence: 1,
            schema_version: 2,
            created_at: "2026-04-24T09:00:00Z",
            type: "message",
            payload: {
              role: "assistant",
              parts: [
                { id: "text-1", type: "text", text: "Starting the workflow." },
              ],
            },
          },
        },
      },
    ]
      .map((event) => JSON.stringify(event))
      .join("\n")

    renderWithProviders(
      <DemoReplayProvider recording={recording} autoPlay={false}>
        <DemoPage />
      </DemoReplayProvider>,
    )

    fireEvent.click(screen.getByRole("button", { name: "Start Demo" }))
    expect(
      screen.getByRole("button", { name: "Pause Demo" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("progressbar", { name: "Demo progress" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("banner")).toHaveClass("flex-wrap")
    fireEvent.click(screen.getByRole("button", { name: "Pause Demo" }))
    fireEvent.click(screen.getByRole("button", { name: "Restart Demo" }))
    await act(async () => vi.runAllTimersAsync())

    expect(
      screen.getByRole("region", { name: "Conversation" }),
    ).toHaveTextContent("Starting the workflow.")
    expect(screen.getByText("Demo complete")).toBeInTheDocument()
  })
})
