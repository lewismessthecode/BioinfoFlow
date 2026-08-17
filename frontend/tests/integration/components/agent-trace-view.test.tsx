import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { AgentTraceView } from "@/components/bioinfoflow/agent/agent-trace-view"
import type {
  AgentTraceEventDetail,
  AgentTraceViewModel,
} from "@/lib/agent/trace-model/types"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${JSON.stringify(values)}` : key,
}))

const view: AgentTraceViewModel = {
  protocolVersion: 1,
  session: {
    id: "session-1",
    title: "RNA-seq review",
    status: "active",
    model: {
      provider: "openai",
      model: "gpt-5.6",
      displayName: "GPT-5.6",
    },
  },
  preambleEvents: [],
  turns: [
    {
      id: "turn-1",
      runId: "run-1",
      index: 1,
      status: "completed",
      model: null,
      events: [
        {
          id: "entry:user-1",
          turnId: "turn-1",
          category: "user",
          title: "User",
          summary: "Run the workflow",
          firstLine: "Run the workflow",
          status: "completed",
          sequence: 1,
          hasDetail: false,
          createdAt: "2026-08-17T08:00:00.000Z",
          phase: "user_input",
        },
        {
          id: "entry:tool-1",
          turnId: "turn-1",
          category: "tool",
          title: "nextflow_run",
          summary: "nextflow_run({ pipeline: 'main.nf' })\nraw second line",
          firstLine: "nextflow_run({ pipeline: 'main.nf' })",
          status: "completed",
          sequence: 2,
          hasDetail: true,
          createdAt: "2026-08-17T08:00:03.000Z",
          phase: "agent_work",
        },
      ],
    },
  ],
  contextFlow: [
    {
      id: "context-1",
      turnId: "turn-1",
      modelTraceId: "model:trace-1",
      sequence: 1,
      throughSequence: 2,
      compacted: false,
      inputTokens: null,
      cachedInputTokens: null,
      maxContextTokens: null,
      composition: [
        { category: "system", characters: 120, tokens: null },
        { category: "user", characters: 40, tokens: null },
      ],
    },
  ],
  eventCount: 2,
}

const detail: AgentTraceEventDetail = {
  protocolVersion: 1,
  eventId: "entry:tool-1",
  summary: {
    category: "tool",
    parent_event_id: "model:trace-1",
  },
  payload: {
    name: "nextflow_run",
    arguments: { pipeline: "main.nf" },
  },
  result: { run_id: "run-1", status: "completed" },
  schema: { type: "object", required: ["pipeline"] },
  timing: {
    startedAt: "2026-08-17T08:00:01.000Z",
    completedAt: "2026-08-17T08:00:03.000Z",
    durationMs: 2000,
  },
}

describe("AgentTraceView", () => {
  it("renders the compact Event Rail without fabricating usage or precise time", () => {
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={vi.fn()} />,
    )

    expect(screen.getByRole("region", { name: "contextFlow.label" })).toBeInTheDocument()
    expect(screen.queryByText(/128K|cached/i)).not.toBeInTheDocument()
    expect(screen.getByText("nextflow_run({ pipeline: 'main.nf' })")).toBeInTheDocument()
    expect(screen.queryByText("2026-08-17T08:00:03.000Z")).not.toBeInTheDocument()
    expect(screen.getByText("phase.agent_work")).toBeInTheDocument()
  })

  it("opens the inspector for a Tool event and exposes all five exact-detail tabs", async () => {
    const user = userEvent.setup()
    const loadDetail = vi.fn().mockResolvedValue(detail)
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={loadDetail} />,
    )

    await user.click(
      screen.getByRole("button", {
        name: "event.openDetail:{\"title\":\"nextflow_run\"}",
      }),
    )

    expect(loadDetail).toHaveBeenCalledWith("entry:tool-1")
    expect(await screen.findByRole("complementary", { name: "inspector.label" })).toBeInTheDocument()
    for (const tab of ["summary", "payload", "result", "schema", "timing"]) {
      expect(screen.getByRole("tab", { name: `inspector.tabs.${tab}` })).toBeInTheDocument()
    }

    await user.click(screen.getByRole("tab", { name: "inspector.tabs.payload" }))
    expect(screen.getByText(/"name": "nextflow_run"/)).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: "inspector.tabs.timing" }))
    expect(screen.getByText("2026-08-17T08:00:01.000Z")).toBeInTheDocument()
  })

  it("weights the append flow by request usage and moves its playhead by trace sequence", async () => {
    const user = userEvent.setup()
    const metricView: AgentTraceViewModel = {
      ...view,
      turns: [
        {
          ...view.turns[0],
          events: [
            {
              id: "assistant:work",
              turnId: "turn-1",
              category: "assistant",
              title: "Assistant",
              summary: "Working",
              firstLine: "Working",
              status: "completed",
              sequence: 5,
              hasDetail: false,
              createdAt: "2026-08-17T08:00:01.000Z",
              phase: "agent_work",
            },
            { ...view.turns[0].events[1], sequence: 8 },
            {
              id: "assistant:final",
              turnId: "turn-1",
              category: "assistant",
              title: "Final answer",
              summary: "Done",
              firstLine: "Done",
              status: "completed",
              sequence: 13,
              hasDetail: false,
              createdAt: "2026-08-17T08:00:04.000Z",
              phase: "final_response",
            },
          ],
        },
      ],
      contextFlow: [
        {
          ...view.contextFlow[0],
          id: "context-early",
          sequence: 3,
          throughSequence: 2,
          inputTokens: 100,
          cachedInputTokens: 50,
          maxContextTokens: 1000,
        },
        {
          ...view.contextFlow[0],
          id: "context-late",
          sequence: 7,
          throughSequence: 4,
          inputTokens: 300,
          cachedInputTokens: 150,
          maxContextTokens: 1000,
        },
        {
          ...view.contextFlow[0],
          id: "context-fallback",
          sequence: 12,
          throughSequence: 9,
          inputTokens: null,
          cachedInputTokens: null,
          maxContextTokens: null,
          composition: [
            { category: "system", characters: 400, tokens: null },
            { category: "user", characters: 200, tokens: null },
          ],
        },
      ],
    }

    renderWithProviders(
      <AgentTraceView view={metricView} onLoadDetail={vi.fn()} />,
    )

    const early = screen.getByRole("button", {
      name: 'contextFlow.snapshot:{"id":"context-early"}',
    })
    const late = screen.getByRole("button", {
      name: 'contextFlow.snapshot:{"id":"context-late"}',
    })
    const fallback = screen.getByRole("button", {
      name: 'contextFlow.snapshot:{"id":"context-fallback"}',
    })

    expect(early).toHaveStyle({ flexGrow: "100" })
    expect(late).toHaveStyle({ flexGrow: "300" })
    expect(fallback).toHaveStyle({ flexGrow: "600" })
    expect(fallback).toHaveAttribute("aria-current", "true")

    await user.click(
      screen.getByRole("button", {
        name: "event.select:{\"title\":\"Assistant\"}",
      }),
    )
    expect(screen.getByText("100 / 1K")).toBeInTheDocument()
    expect(screen.getByText('contextFlow.cached:{"count":"50"}')).toBeInTheDocument()
    expect(early).toHaveAttribute("aria-current", "true")

    await user.click(late)
    expect(screen.getByText("300 / 1K")).toBeInTheDocument()
    expect(late).toHaveAttribute("aria-current", "true")
  })
})
