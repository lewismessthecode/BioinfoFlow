import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AgentTraceView } from "@/components/bioinfoflow/agent/agent-trace-view"
import type {
  AgentTraceEventDetail,
  AgentTraceViewModel,
} from "@/lib/agent/trace-model/types"
import { renderWithProviders } from "@/tests/test-utils"

const mocks = vi.hoisted(() => ({ inspectorInline: true }))

vi.mock("@/hooks/use-media-query", () => ({
  useMediaQuery: () => mocks.inspectorInline,
}))

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
      outputTokens: null,
      cachedInputTokens: null,
      reasoningTokens: null,
      totalTokens: null,
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
    arguments: { pipeline: "payload-only-secret.nf" },
  },
  result: { run_id: "result-only-secret", status: "completed" },
  schema: { type: "schema-only-secret", required: ["pipeline"] },
  timing: {
    startedAt: "2026-08-17T08:00:01.000Z",
    requestPreparedAt: "2026-08-17T08:00:01.100Z",
    firstByteAt: "2026-08-17T08:00:01.300Z",
    completedAt: "2026-08-17T08:00:03.000Z",
    durationMs: 2000,
  },
}

describe("AgentTraceView", () => {
  beforeEach(() => {
    mocks.inspectorInline = true
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("renders an unavailable Context Window without fabricating capacity or precise time", () => {
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={vi.fn()} />,
    )

    expect(screen.getByRole("region", { name: "contextWindow.label" })).toBeInTheDocument()
    expect(screen.getByTestId("context-window-track")).toHaveAttribute(
      "data-state",
      "unavailable",
    )
    expect(screen.getByText("contextWindow.limitUnavailable")).toBeInTheDocument()
    expect(screen.queryByText(/128K|cached/i)).not.toBeInTheDocument()
    expect(screen.getByText("nextflow_run({ pipeline: 'main.nf' })")).toBeInTheDocument()
    expect(screen.queryByText("2026-08-17T08:00:03.000Z")).not.toBeInTheDocument()
    expect(screen.queryByText("phase.agent_work")).not.toBeInTheDocument()
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

    expect(screen.queryByText(/payload-only-secret/)).not.toBeInTheDocument()
    expect(screen.queryByText(/result-only-secret/)).not.toBeInTheDocument()
    expect(screen.queryByText(/schema-only-secret/)).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: "inspector.tabs.payload" }))
    expect(screen.getByText(/"name": "nextflow_run"/)).toBeInTheDocument()
    expect(screen.getByText(/payload-only-secret/)).toBeInTheDocument()
    expect(screen.queryByText(/result-only-secret/)).not.toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: "inspector.tabs.timing" }))
    expect(screen.queryByText(/payload-only-secret/)).not.toBeInTheDocument()
    expect(screen.getByText("2026-08-17T08:00:01.100Z")).toBeInTheDocument()
    expect(screen.getByText("2026-08-17T08:00:01.300Z")).toBeInTheDocument()
    expect(
      screen.getAllByText('units.durationMs:{"value":2000}'),
    ).toHaveLength(2)
  })

  it("surfaces a failed Tool diagnosis before the Inspector tabs", async () => {
    const user = userEvent.setup()
    const failedView: AgentTraceViewModel = {
      ...view,
      turns: [
        {
          ...view.turns[0],
          events: [
            {
              ...view.turns[0].events[1],
              status: "failed",
              title: "bash",
              summary: "bash({ command: 'pwd' })",
              firstLine: "bash({ command: 'pwd' })",
            },
          ],
        },
      ],
    }
    const failedDetail: AgentTraceEventDetail = {
      ...detail,
      summary: { category: "tool", name: "bash", status: "failed" },
      result: { error: "Working directory does not exist" },
      timing: { ...detail.timing!, durationMs: 1800 },
    }

    renderWithProviders(
      <AgentTraceView
        view={failedView}
        onLoadDetail={vi.fn().mockResolvedValue(failedDetail)}
      />,
    )

    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"bash"}',
      }),
    )

    const inspector = await screen.findByRole("complementary", {
      name: "inspector.label",
    })
    expect(inspector).toHaveClass("w-[400px]")
    expect(within(inspector).getByText("status.failed")).not.toHaveClass("hidden")
    expect(
      within(inspector).getByText("Working directory does not exist"),
    ).toBeInTheDocument()
    expect(
      within(inspector).getByText('units.durationMs:{"value":1800}'),
    ).toBeInTheDocument()
  })

  it("separates Context Window capacity from Turn-grouped request navigation", async () => {
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
            {
              id: "model:request-1",
              turnId: "turn-1",
              category: "context",
              title: "Model request",
              summary: "openai/gpt-5.6 · 100 input tokens",
              firstLine: "openai/gpt-5.6 · 100 input tokens",
              status: "completed",
              sequence: 3,
              hasDetail: true,
              createdAt: "2026-08-17T08:00:01.500Z",
              phase: "model_request",
            },
            { ...view.turns[0].events[1], sequence: 8 },
          ],
        },
        {
          ...view.turns[0],
          id: "turn-2",
          runId: "run-2",
          index: 2,
          events: [
            {
              id: "assistant:final",
              turnId: "turn-2",
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
          outputTokens: 20,
          cachedInputTokens: 50,
          reasoningTokens: 4,
          totalTokens: 120,
          maxContextTokens: 1000,
        },
        {
          ...view.contextFlow[0],
          id: "context-late",
          sequence: 7,
          throughSequence: 4,
          inputTokens: 300,
          outputTokens: 40,
          cachedInputTokens: 150,
          reasoningTokens: 8,
          totalTokens: 340,
          maxContextTokens: 1000,
        },
        {
          ...view.contextFlow[0],
          id: "context-fallback",
          turnId: "turn-2",
          sequence: 12,
          throughSequence: 9,
          inputTokens: 600,
          outputTokens: 60,
          cachedInputTokens: 250,
          reasoningTokens: 12,
          totalTokens: 900,
          maxContextTokens: 1000,
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

    const navigator = screen.getByRole("navigation", {
      name: "requestNavigator.label",
    })
    const early = within(navigator).getByRole("button", {
      name: 'requestNavigator.request:{"turn":1,"index":1}',
    })
    const late = within(navigator).getByRole("button", {
      name: 'requestNavigator.request:{"turn":1,"index":2}',
    })
    const fallback = within(navigator).getByRole("button", {
      name: 'requestNavigator.request:{"turn":2,"index":1}',
    })

    expect(
      within(navigator).getAllByText('turn:{"index":1}'),
    ).toHaveLength(1)
    expect(
      within(navigator).getAllByText('turn:{"index":2}'),
    ).toHaveLength(1)
    expect(fallback).toHaveAttribute("aria-current", "true")
    expect(screen.getByTestId("context-window-used")).toHaveStyle({
      width: "60%",
    })
    expect(
      screen.getByText(
        'contextWindow.usedOfLimit:{"used":"600","limit":"units.thousand:{\\"value\\":\\"1\\"}"}',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('contextWindow.percent:{"value":60}')).toBeInTheDocument()
    expect(screen.getByText('contextWindow.cached:{"count":"250"}')).toBeInTheDocument()
    expect(screen.getByText("contextWindow.compositionEstimated")).toBeInTheDocument()

    await user.click(
      screen.getByRole("button", {
        name: "event.select:{\"title\":\"Assistant\"}",
      }),
    )
    expect(early).toHaveAttribute("aria-current", "true")
    expect(screen.getByTestId("context-window-used")).toHaveStyle({
      width: "10%",
    })
    expect(
      screen.queryByText('contextWindow.percent:{"value":12}'),
    ).not.toBeInTheDocument()

    await user.click(late)
    expect(screen.getByTestId("context-window-used")).toHaveStyle({
      width: "30%",
    })
    expect(late).toHaveAttribute("aria-current", "true")

    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"Model request"}',
      }),
    )
    expect(early).toHaveAttribute("aria-current", "true")
    expect(screen.getByTestId("context-window-used")).toHaveStyle({
      width: "10%",
    })
  })

  it("localizes finite category and status labels while preserving unknown status text", () => {
    const localizedView: AgentTraceViewModel = {
      ...view,
      turns: [
        {
          ...view.turns[0],
          events: [
            view.turns[0].events[1],
            {
              ...view.turns[0].events[1],
              id: "entry:tool-unknown",
              status: "waiting_on_cluster",
              sequence: 3,
            },
          ],
        },
      ],
    }

    renderWithProviders(
      <AgentTraceView view={localizedView} onLoadDetail={vi.fn()} />,
    )

    expect(screen.getAllByText("category.tool")).toHaveLength(2)
    expect(screen.getByText("status.completed")).toBeInTheDocument()
    expect(screen.getByText("waiting_on_cluster")).toBeInTheDocument()
  })

  it("localizes event titles from stable codes instead of backend fallback text", async () => {
    const user = userEvent.setup()
    const localizedTitleView: AgentTraceViewModel = {
      ...view,
      turns: [
        {
          ...view.turns[0],
          events: [
            {
              ...view.turns[0].events[1],
              title: "Tool result",
              titleCode: "agentTrace.event.toolResult",
              titleParams: {},
            },
          ],
        },
      ],
    }

    renderWithProviders(
      <AgentTraceView
        view={localizedTitleView}
        onLoadDetail={vi.fn().mockResolvedValue(detail)}
      />,
    )

    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"eventTitles.toolResult"}',
      }),
    )

    expect(
      within(
        await screen.findByRole("complementary", { name: "inspector.label" }),
      ).getByText("eventTitles.toolResult"),
    ).toBeInTheDocument()
  })

  it("uses one safe narrow-screen inspector close action", async () => {
    mocks.inspectorInline = false
    const user = userEvent.setup()
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={vi.fn().mockResolvedValue(detail)} />,
    )

    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"nextflow_run"}',
      }),
    )

    const dialog = await screen.findByRole("dialog")
    expect(dialog).toHaveClass("overscroll-contain")
    expect(dialog.className).toContain("safe-area-inset")
    expect(
      screen.getAllByRole("button", { name: "inspector.close" }),
    ).toHaveLength(1)
  })

  it("uses the Sheet when the trace container is too narrow for an inline inspector", async () => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(private readonly callback: ResizeObserverCallback) {}

        observe() {
          this.callback(
            [{ contentRect: { width: 800 } } as ResizeObserverEntry],
            this as unknown as ResizeObserver,
          )
        }

        disconnect() {}

        unobserve() {}
      },
    )
    const user = userEvent.setup()
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={vi.fn().mockResolvedValue(detail)} />,
    )

    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"nextflow_run"}',
      }),
    )

    expect(await screen.findByRole("dialog")).toBeInTheDocument()
    expect(
      screen.queryByRole("complementary", { name: "inspector.label" }),
    ).not.toBeInTheDocument()
  })

  it("retries a failed detail request from the inspector", async () => {
    const user = userEvent.setup()
    const loadDetail = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(detail)
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={loadDetail} />,
    )

    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"nextflow_run"}',
      }),
    )
    expect(await screen.findByRole("alert")).toHaveTextContent("detailError")

    await user.click(screen.getByRole("button", { name: "retry" }))

    expect(loadDetail).toHaveBeenCalledTimes(2)
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument())
  })

  it("allows a long single-line event to expand without changing weighted layout", () => {
    const longSummary = `nextflow_run(${"x".repeat(180)})`
    const longView: AgentTraceViewModel = {
      ...view,
      turns: [
        {
          ...view.turns[0],
          events: [
            {
              ...view.turns[0].events[1],
              summary: longSummary,
              firstLine: longSummary,
            },
          ],
        },
      ],
    }

    renderWithProviders(
      <AgentTraceView view={longView} onLoadDetail={vi.fn()} />,
    )

    expect(
      screen.getByRole("button", {
        name: 'event.expand:{"title":"nextflow_run"}',
      }),
    ).toBeInTheDocument()
    expect(screen.getByRole("region", { name: 'turn:{"index":1}' })).toHaveClass(
      "[content-visibility:auto]",
    )
  })

  it("marks technical trace values as non-translatable", async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <AgentTraceView view={view} onLoadDetail={vi.fn().mockResolvedValue(detail)} />,
    )

    expect(screen.getByText("category.tool")).toHaveAttribute("translate", "no")
    expect(
      screen.getByText("nextflow_run({ pipeline: 'main.nf' })"),
    ).toHaveAttribute("translate", "no")
    expect(
      screen
        .getAllByText("status.completed")
        .every((item) => item.closest("span[translate='no']") !== null),
    ).toBe(true)
    await user.click(
      screen.getByRole("button", {
        name: 'event.openDetail:{"title":"nextflow_run"}',
      }),
    )
    await user.click(screen.getByRole("tab", { name: "inspector.tabs.payload" }))

    expect(screen.getByText("entry:tool-1")).toHaveAttribute("translate", "no")
    expect(screen.getByText(/payload-only-secret/)).toHaveAttribute(
      "translate",
      "no",
    )
  })
})
