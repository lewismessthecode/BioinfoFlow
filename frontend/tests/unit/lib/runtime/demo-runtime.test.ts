import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { createDemoRuntime, setActiveRuntimeForTests } from "@/lib/runtime"
import type {
  AgentEventData,
  EventEnvelope,
  Project,
  Run,
  RunStatusEvent,
  Workflow,
} from "@/lib/types"

describe("createDemoRuntime", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    setActiveRuntimeForTests(null)
  })

  it("serves seeded projects and workflows", async () => {
    const runtime = createDemoRuntime()

    const projects = await runtime.request<Project[]>("/projects", {
      params: { limit: 100 },
    })
    const workflows = await runtime.request<Workflow[]>("/workflows", {
      params: { limit: 100 },
    })

    expect(projects.data).toHaveLength(1)
    expect(projects.data[0]?.name).toContain("Demo")
    expect(workflows.data.length).toBeGreaterThan(0)
    expect(
      workflows.data.some((workflow) => workflow.id === "wf-rnaseq-quant-mini"),
    ).toBe(true)
  })

  it("creates a mock run and replays status events", async () => {
    const runtime = createDemoRuntime()
    const onRunStatus = vi.fn<(event: { data: RunStatusEvent }) => void>()

    const unsubscribe = runtime.subscribe({
      projectId: "project-demo",
      onRunStatus,
    })

    const response = await runtime.request<{ run_id: string }>("/runs", {
      method: "POST",
      body: JSON.stringify({
        project_id: "project-demo",
        workflow_id: "wf-rnaseq-quant-mini",
        values: {
          reads_r1: "deliveries/ecoli_R1.fastq.gz",
          reads_r2: "deliveries/ecoli_R2.fastq.gz",
          reference: "reference/ecoli_k12.fa",
        },
      }),
    })

    const runs = await runtime.request<Run[]>("/runs", {
      params: { project_id: "project-demo", limit: 20 },
    })

    expect(response.data.run_id).toBe("run_demo_001")
    expect(runs.data.some((run) => run.run_id === "run_demo_001")).toBe(true)

    await vi.runAllTimersAsync()

    expect(onRunStatus).toHaveBeenCalled()
    expect(
      onRunStatus.mock.calls.some(
        ([event]) =>
          event.data.run_id === "run_demo_001" &&
          event.data.status === "completed",
      ),
    ).toBe(true)

    unsubscribe()
  })

  it("accepts an agent message and replays scripted agent events", async () => {
    const runtime = createDemoRuntime()
    const onAgentEvent = vi.fn<(event: EventEnvelope<AgentEventData>) => void>()

    const unsubscribe = runtime.subscribe({
      projectId: "project-demo",
      onAgentEvent,
    })

    const response = await runtime.request<{
      conversation_id: string
      response_id: string
      message_id: string
      status: string
    }>("/agent/message", {
      method: "POST",
      body: JSON.stringify({
        project_id: "project-demo",
        content: "Run the seeded RNA-seq demo.",
      }),
    })

    expect(response.data.conversation_id).toBe("conv-demo-main")
    expect(response.data.status).toBe("accepted")

    await vi.runAllTimersAsync()

    expect(
      onAgentEvent.mock.calls.some(
        ([event]) =>
          event.event === "agent.text_delta" &&
          event.data.content?.includes("live deck and runs view"),
      ),
    ).toBe(true)
    expect(
      onAgentEvent.mock.calls.some(([event]) => event.event === "agent.done"),
    ).toBe(true)

    unsubscribe()
  })
})
