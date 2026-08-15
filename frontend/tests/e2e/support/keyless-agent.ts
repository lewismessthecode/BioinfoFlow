import type { APIRequestContext, TestInfo } from "@playwright/test"

export type KeylessAgentScenario =
  | "streaming"
  | "plan"
  | "parallel-tools"
  | "serial-tools"
  | "approval"
  | "ask-user"
  | "stop"
  | "recovery"

type SuccessEnvelope<T> = {
  success: true
  data: T
}

type ProviderSetupResult = {
  models: Array<{ id: string; model_id: string }>
}

type ProviderListResult = Array<{ id: string; enabled: boolean }>

type AgentSessionSnapshot = {
  session: { id: string }
  runs: Array<{ id: string; status: string }>
  active_run: {
    run: { id: string; status: string }
  } | null
  entries: Array<Record<string, unknown>>
}

const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const modelPort = Number(process.env.PLAYWRIGHT_MODEL_PORT || 9100)
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`

const scenarioModelPrefix: Record<KeylessAgentScenario, string> = {
  streaming: "e2e-reasoning-stream",
  plan: "e2e-plan",
  "parallel-tools": "e2e-parallel-tools",
  "serial-tools": "e2e-serial-tools",
  approval: "e2e-approval",
  "ask-user": "e2e-ask-user",
  stop: "e2e-stop",
  recovery: "e2e-recovery",
}

export async function disableKeylessAgentProviders(
  request: APIRequestContext,
): Promise<void> {
  const response = await request.get(`${apiBaseUrl}/llm/providers`)
  const providers = await requireSuccess<ProviderListResult>(
    response,
    "list providers",
  )
  for (const provider of providers) {
    if (!provider.enabled) continue
    const disabled = await request.patch(
      `${apiBaseUrl}/llm/providers/${provider.id}`,
      { data: { enabled: false } },
    )
    await requireSuccess(disabled, `disable provider ${provider.id}`)
  }
}

export async function setupKeylessAgentModel(
  request: APIRequestContext,
  scenario: KeylessAgentScenario,
  testInfo: TestInfo,
): Promise<string> {
  const suffix = safeIdentifier(
    `${testInfo.project.name}-${testInfo.workerIndex}-${testInfo.retry}`,
  )
  const modelId = `${scenarioModelPrefix[scenario]}-${suffix}`
  const response = await request.post(`${apiBaseUrl}/llm/provider-setups`, {
    data: {
      template_id: "openai-compatible",
      name: `Keyless Agent E2E ${scenario} ${suffix}`,
      base_url: `http://127.0.0.1:${modelPort}/v1`,
      wire_protocol: "chat_completions",
      api_key: "e2e-test-key",
      model_ids: [modelId],
      discover: false,
      enabled: true,
      allow_insecure_http: true,
    },
  })
  const payload = await requireSuccess<ProviderSetupResult>(response, "setup provider")
  const model = payload.models.find((item) => item.model_id === modelId)
  if (!model) {
    throw new Error(`Provider setup did not return model ${modelId}`)
  }
  return model.id
}

export async function createKeylessAgentSession(
  request: APIRequestContext,
  input: {
    modelId: string
    permissionMode?: "ask_changes" | "ask_dangerous" | "full_access"
    workspaceAccess?: "read_only" | "read_write"
  },
): Promise<AgentSessionSnapshot> {
  const response = await request.post(`${apiBaseUrl}/agent/sessions`, {
    data: {
      model_id: input.modelId,
      permission_mode: input.permissionMode ?? "ask_dangerous",
      workspace_access: input.workspaceAccess ?? "read_write",
    },
  })
  return requireSuccess<AgentSessionSnapshot>(response, "create Agent session")
}

export async function dispatchKeylessAgentMessage(
  request: APIRequestContext,
  sessionId: string,
  text: string,
): Promise<AgentSessionSnapshot> {
  const response = await request.post(
    `${apiBaseUrl}/agent/sessions/${sessionId}/commands`,
    {
      data: {
        type: "message",
        command_id: `e2e-message-${crypto.randomUUID()}`,
        parts: [{ type: "text", text }],
      },
    },
  )
  return requireSuccess<AgentSessionSnapshot>(response, "dispatch Agent prompt")
}

export async function getKeylessAgentSnapshot(
  request: APIRequestContext,
  sessionId: string,
): Promise<AgentSessionSnapshot> {
  const response = await request.get(
    `${apiBaseUrl}/agent/sessions/${sessionId}/snapshot`,
  )
  return requireSuccess<AgentSessionSnapshot>(response, "get Agent snapshot")
}

export async function restartKeylessBackend(
  request: APIRequestContext,
  options: { offlineMilliseconds?: number } = {},
): Promise<void> {
  const controlPort = Number(
    process.env.PLAYWRIGHT_BACKEND_CONTROL_PORT || backendPort + 1,
  )
  const response = await request.post(
    `http://127.0.0.1:${controlPort}/restart`,
    {
      data: {
        offline_milliseconds: options.offlineMilliseconds ?? 0,
      },
      timeout: 30_000,
    },
  )
  if (!response.ok()) {
    throw new Error(
      `restart Agent backend failed with ${response.status()}: ${await response.text()}`,
    )
  }
}

async function requireSuccess<T>(
  response: Awaited<ReturnType<APIRequestContext["get"]>>,
  operation: string,
): Promise<T> {
  if (!response.ok()) {
    throw new Error(
      `${operation} failed with ${response.status()}: ${await response.text()}`,
    )
  }
  const envelope = (await response.json()) as SuccessEnvelope<T>
  return envelope.data
}

function safeIdentifier(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
}
