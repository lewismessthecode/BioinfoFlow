import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { createDemoRuntime, setActiveRuntimeForTests } from "@/lib/runtime"
import type {
  Project,
  Run,
  RunStatusEvent,
  Workflow,
} from "@/lib/types"
import type {
  AgentCoreAction,
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreSession,
  AgentCoreSkill,
  AgentCoreTurn,
} from "@/lib/agent-core"
import type {
  LlmConfiguration,
  LlmModel,
  LlmModelProfile,
  LlmProvider,
  LlmProviderSetupResult,
  LlmProviderTemplate,
  LlmProviderTestResult,
} from "@/lib/llm"

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

  it("updates AgentCore session permission mode", async () => {
    const runtime = createDemoRuntime()
    const created = await runtime.request<AgentCoreSession>("/agent/sessions", {
      method: "POST",
      body: JSON.stringify({
        project_id: "project-demo",
        permission_mode: "guarded_auto",
        automation_mode: "assisted",
      }),
    })

    const updated = await runtime.request<AgentCoreSession>(
      `/agent/sessions/${created.data.id}`,
      {
        method: "PATCH",
        body: JSON.stringify({ permission_mode: "bypass" }),
      },
    )

    expect(updated.data.permission_mode).toBe("bypass")
  })

  it("creates an AgentCore turn and exposes the event ledger", async () => {
    const runtime = createDemoRuntime()

    const sessionResponse = await runtime.request<AgentCoreSession>(
      "/agent/sessions",
      {
        method: "POST",
        body: JSON.stringify({
          project_id: "project-demo",
          title: "AgentCore demo",
          permission_mode: "guarded_auto",
          automation_mode: "assisted",
        }),
      },
    )
    const skillsResponse = await runtime.request<{ skills: AgentCoreSkill[] }>(
      "/agent/skills",
    )
    const turnResponse = await runtime.request<AgentCoreTurn>(
      `/agent/sessions/${sessionResponse.data.id}/turns`,
      {
        method: "POST",
        body: JSON.stringify({
          input_text: "Run the seeded RNA-seq demo.",
          active_skill_names: ["nextflow-debugging"],
        }),
      },
    )
    const eventsResponse = await runtime.request<AgentCoreEvent[]>(
      `/agent/turns/${turnResponse.data.id}/events`,
    )
    const artifactsResponse = await runtime.request<AgentCoreArtifact[]>(
      `/agent/turns/${turnResponse.data.id}/artifacts`,
    )
    const memoriesResponse = await runtime.request<AgentCoreMemory[]>(
      "/agent/memories",
      {
        params: {
          project_id: "project-demo",
          status: "proposed",
        },
      },
    )
    const actionId = String(
      eventsResponse.data.find((event) => event.type === "action.waiting_decision")
        ?.payload.action_id,
    )
    const actionDecisionResponse = await runtime.request<AgentCoreAction>(
      `/agent/actions/${actionId}/decision`,
      {
        method: "POST",
        body: JSON.stringify({
          decision: "approve",
        }),
      },
    )
    const memoryDecisionResponse = await runtime.request<AgentCoreMemory>(
      `/agent/memories/${memoriesResponse.data[0]?.id}/accept`,
      {
        method: "POST",
      },
    )
    const rejectedLegacyMessage = runtime.request("/agent/message", {
      method: "POST",
      body: JSON.stringify({
        project_id: "project-demo",
        content: "Run the seeded RNA-seq demo.",
      }),
    })

    await expect(rejectedLegacyMessage).rejects.toMatchObject({ status: 404 })
    expect(sessionResponse.data.id).toMatch(/^agent-session-demo-/)
    expect(skillsResponse.data.skills.map((skill) => skill.name)).toEqual([
      "nextflow-debugging",
      "run-failure-triage",
    ])
    expect(turnResponse.data.status).toBe("completed")
    expect(turnResponse.data.active_skill_names).toEqual(["nextflow-debugging"])
    expect(turnResponse.data.final_text).toContain("seeded RNA-seq demo workflow")
    expect(eventsResponse.data.map((event) => event.type)).toEqual([
      "turn.created",
      "turn.started",
      "assistant.thinking.summary",
      "user_input.requested",
      "user_input.resolved",
      "action.requested",
      "action.waiting_decision",
      "action.completed",
      "artifact.created",
      "memory.proposed",
      "assistant.text.completed",
      "turn.completed",
    ])
    expect(artifactsResponse.data[0]?.title).toContain("demo run")
    expect(
      eventsResponse.data.find((event) => event.type === "user_input.requested")
        ?.payload.question,
    ).toContain("reference")
    expect(memoriesResponse.data[0]?.type).toBe("run_lesson")
    expect(actionDecisionResponse.data.permission_decision).toMatchObject({
      decision: "approve",
    })
    expect(memoryDecisionResponse.data.status).toBe("accepted")

    await vi.runAllTimersAsync()
  })

  it("serves platform LLM catalog endpoints in demo mode", async () => {
    const runtime = createDemoRuntime()

    const providersResponse = await runtime.request<LlmProvider[]>("/llm/providers")
    const configurationResponse = await runtime.request<LlmConfiguration>(
      "/llm/configuration",
    )
    const templatesResponse = await runtime.request<LlmProviderTemplate[]>(
      "/llm/provider-templates",
    )
    const modelsResponse = await runtime.request<LlmModel[]>("/llm/models")
    const profilesResponse = await runtime.request<LlmModelProfile[]>(
      "/llm/model-profiles",
    )
    const testResponse = await runtime.request<LlmProviderTestResult>(
      `/llm/providers/${providersResponse.data[0]?.id}/test`,
      { method: "POST" },
    )
    const createdResponse = await runtime.request<LlmProvider>("/llm/providers", {
      method: "POST",
      body: JSON.stringify({
        name: "OpenRouter Shared",
        kind: "openrouter",
        base_url: "https://openrouter.ai/api/v1",
        api_key_ref: "env:OPENROUTER_API_KEY",
        scope: "workspace",
      }),
    })
    const setupResponse = await runtime.request<LlmProviderSetupResult>(
      "/llm/provider-setups",
      {
        method: "POST",
        body: JSON.stringify({
          template_id: "vllm",
          base_url: "http://localhost:8000/v1",
          model_ids: ["deepseek_v4"],
          scope: "user",
        }),
      },
    )

    expect(providersResponse.data[0]?.name).toBe("Demo OpenAI Compatible")
    expect(configurationResponse.data.providers[0]?.credential.available).toBe(true)
    expect(templatesResponse.data.some((template) => template.id === "vllm")).toBe(true)
    expect(modelsResponse.data[0]?.display_name).toBe("Demo Bio Coder")
    expect(profilesResponse.data[0]?.task_type).toBe("agent_core")
    expect(testResponse.data.success).toBe(true)
    expect(createdResponse.data.name).toBe("OpenRouter Shared")
    expect(setupResponse.data.provider.name).toBe("vLLM")
    expect(setupResponse.data.models[0]?.model_id).toBe("deepseek_v4")
  })

  it("round-trips provider protocol and transport settings in demo mode", async () => {
    const runtime = createDemoRuntime()

    const templatesResponse = await runtime.request<LlmProviderTemplate[]>(
      "/llm/provider-templates",
    )
    const compatibleTemplate = templatesResponse.data.find(
      (template) => template.id === "openai-compatible",
    )
    expect(compatibleTemplate?.supported_wire_protocols).toEqual([
      "chat_completions",
      "responses",
    ])
    expect(compatibleTemplate?.default_wire_protocol).toBe("chat_completions")

    const setupResponse = await runtime.request<LlmProviderSetupResult>(
      "/llm/provider-setups",
      {
        method: "POST",
        body: JSON.stringify({
          template_id: "openai-compatible",
          base_url: "http://relay.example:8079/v1",
          wire_protocol: "responses",
          allow_insecure_http: true,
          model_ids: ["gpt-demo"],
          scope: "user",
        }),
      },
    )
    expect(setupResponse.data.provider).toMatchObject({
      wire_protocol: "responses",
      allow_insecure_http: true,
    })

    const updatedResponse = await runtime.request<LlmProvider>(
      `/llm/providers/${setupResponse.data.provider.id}`,
      {
        method: "PATCH",
        body: JSON.stringify({
          wire_protocol: "chat_completions",
          allow_insecure_http: false,
        }),
      },
    )
    expect(updatedResponse.data).toMatchObject({
      wire_protocol: "chat_completions",
      allow_insecure_http: false,
    })

    const testResponse = await runtime.request<LlmProviderTestResult>(
      `/llm/providers/${setupResponse.data.provider.id}/test`,
      { method: "POST" },
    )
    expect(testResponse.data).toMatchObject({
      wire_protocol: "chat_completions",
      retryable: false,
      error_code: null,
      http_status: null,
      provider_code: null,
    })

    const configurationResponse = await runtime.request<LlmConfiguration>(
      "/llm/configuration",
    )
    expect(
      configurationResponse.data.providers.find(
        (provider) => provider.id === setupResponse.data.provider.id,
      ),
    ).toMatchObject({
      wire_protocol: "chat_completions",
      allow_insecure_http: false,
      test_status: {
        wire_protocol: "chat_completions",
        retryable: false,
      },
    })
  })

  it("returns complete protocol fields for seeded and directly created providers", async () => {
    const runtime = createDemoRuntime()

    const providersResponse = await runtime.request<LlmProvider[]>("/llm/providers")
    expect(providersResponse.data[0]).toMatchObject({
      wire_protocol: "chat_completions",
      allow_insecure_http: false,
      test_status: {
        model: "demo-bio-coder",
        wire_protocol: "chat_completions",
        retryable: false,
      },
    })

    const createdResponse = await runtime.request<LlmProvider>("/llm/providers", {
      method: "POST",
      body: JSON.stringify({
        name: "Demo Responses Relay",
        kind: "openai_compatible",
        wire_protocol: "responses",
        base_url: "http://relay.example:8079/v1",
        allow_insecure_http: true,
        scope: "user",
      }),
    })
    expect(createdResponse.data).toMatchObject({
      wire_protocol: "responses",
      allow_insecure_http: true,
    })
  })

  it("tests the selected provider model in demo mode", async () => {
    const runtime = createDemoRuntime()
    const setupResponse = await runtime.request<LlmProviderSetupResult>(
      "/llm/provider-setups",
      {
        method: "POST",
        body: JSON.stringify({
          template_id: "openai-compatible",
          model_ids: ["gpt-demo-a", "gpt-demo-b"],
          scope: "user",
        }),
      },
    )
    const selectedModel = setupResponse.data.models.find(
      (model) => model.model_id === "gpt-demo-a",
    )

    const testResponse = await runtime.request<LlmProviderTestResult>(
      `/llm/providers/${setupResponse.data.provider.id}/test`,
      {
        method: "POST",
        body: JSON.stringify({ model_id: selectedModel?.id }),
      },
    )

    expect(testResponse.data.model).toBe("gpt-demo-a")
  })
})
