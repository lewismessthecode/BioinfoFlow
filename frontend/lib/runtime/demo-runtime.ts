import type { RunCreateV2 } from "@/lib/form-spec"
import type {
  AuditLogEntry,
  DagData,
  DockerImage,
  EventEnvelope,
  ImageStatusMeta,
  Project,
  ProjectWorkflowGroup,
  Run,
  RunDagEvent,
  RunLogEntry,
  RunLogs,
  RunOutputs,
  RunStatusEvent,
  ValidateWorkflowResponse,
  Workflow,
} from "@/lib/types"
import type {
  AppRuntime,
  RequestParams,
  RuntimeEventSubscription,
  RuntimeRequestOptions,
  RuntimeRequestResult,
} from "./types"
import { ApiError } from "./request-core"
import { DEMO_RUNTIME_SCENARIO } from "@/lib/demo/scenario-data"
import type { DemoScenario, DemoFileNode } from "@/lib/demo/scenario"
import type {
  AgentCoreAction,
  AgentCoreArtifact,
  AgentAutomationMode,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreSession,
  AgentCoreSkill,
  AgentCoreTurn,
  AgentPermissionMode,
  AgentSessionStatus,
} from "@/lib/agent-core"
import type {
  LlmConfiguration,
  LlmConfiguredProvider,
  LlmProviderCredential,
  LlmModel,
  LlmModelProfile,
  LlmProvider,
  LlmProviderKind,
  LlmProviderScope,
  LlmProviderSetupResult,
  LlmProviderTemplate,
  LlmProviderTestResult,
  LlmWireProtocol,
} from "@/lib/llm"

const DEMO_AGENT_SKILLS: AgentCoreSkill[] = [
  {
    name: "nextflow-debugging",
    version: "0.1.0",
    description: "Diagnose failed Nextflow runs using logs, DAGs, and audit events.",
    category: "workflow",
    tags: ["nextflow", "debugging"],
  },
  {
    name: "run-failure-triage",
    version: "0.1.0",
    description: "Collect Bioinfoflow run evidence before explaining a failure.",
    category: "runs",
    tags: ["runs", "logs"],
  },
]


type DemoRuntimeState = {
  scenario: DemoScenario
  runs: Map<string, Run>
  runLogs: Map<string, RunLogs>
  runOutputs: Map<string, RunOutputs>
  runDag: Map<string, DagData>
  runAudit: Map<string, AuditLogEntry[]>
  agentSessionsByProject: Map<string, AgentCoreSession[]>
  agentTurnsBySession: Map<string, AgentCoreTurn[]>
  agentEventsByTurn: Map<string, AgentCoreEvent[]>
  agentActions: Map<string, AgentCoreAction>
  agentArtifactsByTurn: Map<string, AgentCoreArtifact[]>
  agentMemories: AgentCoreMemory[]
  workflowGroupsByProject: Map<string, ProjectWorkflowGroup[]>
  workspaceFiles: Map<string, DemoFileNode[]>
  images: DockerImage[]
  imageStatus: ImageStatusMeta
  llmProviders: LlmProvider[]
  llmProviderCredentials: Record<string, LlmProviderCredential>
  llmModels: LlmModel[]
  llmModelProfiles: LlmModelProfile[]
  runSequence: number
  projectSequence: number
  workflowSequence: number
  agentSessionSequence: number
  agentTurnSequence: number
  agentEventSequence: number
  agentActionSequence: number
  agentArtifactSequence: number
  agentMemorySequence: number
  imageSequence: number
  llmProviderSequence: number
  subscribers: Map<number, RuntimeEventSubscription>
  subscriptionSequence: number
}

function clone<T>(value: T): T {
  return structuredClone(value)
}

function createInitialState(): DemoRuntimeState {
  const seededAgentSessionsByProject = new Map<string, AgentCoreSession[]>(
    Object.entries(DEMO_RUNTIME_SCENARIO.agentSessions).map(
      ([projectId, sessions]) => [
        projectId,
        clone(sessions),
      ],
    ),
  )

  return {
    scenario: clone(DEMO_RUNTIME_SCENARIO),
    runs: new Map(
      DEMO_RUNTIME_SCENARIO.runs.map((run) => [run.run_id, clone(run)]),
    ),
    runLogs: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runLogs).map(([runId, logs]) => [
        runId,
        clone(logs),
      ]),
    ),
    runOutputs: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runOutputs).map(([runId, outputs]) => [
        runId,
        clone(outputs),
      ]),
    ),
    runDag: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runDag).map(([runId, dag]) => [
        runId,
        clone(dag),
      ]),
    ),
    runAudit: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.runAudit).map(([runId, audit]) => [
        runId,
        clone(audit),
      ]),
    ),
    agentSessionsByProject: seededAgentSessionsByProject,
    agentTurnsBySession: new Map(
      [...seededAgentSessionsByProject.values()]
        .flat()
        .map((session) => [session.id, []]),
    ),
    agentEventsByTurn: new Map(),
    agentActions: new Map(),
    agentArtifactsByTurn: new Map(),
    agentMemories: [],
    workflowGroupsByProject: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.projectWorkflowGroups).map(
        ([projectId, groups]) => [projectId, clone(groups)],
      ),
    ),
    workspaceFiles: new Map(
      Object.entries(DEMO_RUNTIME_SCENARIO.workspaceFiles).map(
        ([projectId, files]) => [projectId, clone(files)],
      ),
    ),
    images: clone(DEMO_RUNTIME_SCENARIO.images),
    imageStatus: clone(DEMO_RUNTIME_SCENARIO.imageStatus),
    llmProviders: [
      {
        id: "llm-provider-demo-001",
        name: "Demo OpenAI Compatible",
        kind: "openai_compatible",
        wire_protocol: "chat_completions",
        base_url: "http://localhost:11434/v1",
        api_key_ref: "env:DEMO_MODEL_KEY",
        scope: "workspace",
        workspace_id: "workspace-demo",
        user_id: null,
        enabled: true,
        allow_insecure_http: false,
        test_status: {
          success: true,
          model: "demo-bio-coder",
          wire_protocol: "chat_completions",
          latency_ms: 24,
          retryable: false,
        },
        metadata: { demo: true, providerTemplate: "openai-compatible" },
        created_at: nowStamp(),
        updated_at: nowStamp(),
      },
    ],
    llmProviderCredentials: {
      "llm-provider-demo-001": {
        provider_id: "llm-provider-demo-001",
        source: "env",
        configured: true,
        available: true,
        env_var_name: "DEMO_MODEL_KEY",
        fingerprint: null,
        masked_hint: "env:DEMO_MODEL_KEY",
        updated_at: nowStamp(),
      },
    },
    llmModels: [
      {
        id: "llm-model-demo-001",
        provider_id: "llm-provider-demo-001",
        model_id: "demo-bio-coder",
        display_name: "Demo Bio Coder",
        context_length: 128000,
        max_output_tokens: 8192,
        supports_tools: true,
        supports_streaming: true,
        supports_vision: false,
        supports_json_schema: true,
        supports_reasoning: true,
        default_temperature: null,
        default_top_p: null,
        cost_metadata: null,
        metadata: { demo: true },
        created_at: nowStamp(),
        updated_at: nowStamp(),
      },
    ],
    llmModelProfiles: [
      {
        id: "llm-profile-demo-001",
        name: "Demo AgentCore default",
        task_type: "agent_core",
        primary_model_id: "llm-model-demo-001",
        fallback_model_ids: [],
        reasoning_budget: 4096,
        max_tokens: 8192,
        cost_ceiling: null,
        routing_policy: { fallback: "on_error" },
        permission_overrides: null,
        scope: "workspace",
        workspace_id: "workspace-demo",
        user_id: null,
        enabled: true,
        metadata: { demo: true },
        created_at: nowStamp(),
        updated_at: nowStamp(),
      },
    ],
    runSequence: 1,
    projectSequence: DEMO_RUNTIME_SCENARIO.projects.length + 1,
    workflowSequence: DEMO_RUNTIME_SCENARIO.workflows.length + 1,
    agentSessionSequence:
      Object.values(DEMO_RUNTIME_SCENARIO.agentSessions).flat().length + 1,
    agentTurnSequence: 1,
    agentEventSequence: 1,
    agentActionSequence: 1,
    agentArtifactSequence: 1,
    agentMemorySequence: 1,
    imageSequence: DEMO_RUNTIME_SCENARIO.images.length + 1,
    subscribers: new Map(),
    subscriptionSequence: 0,
    llmProviderSequence: 2,
  }
}

type DemoRunReplayStep =
  | { delayMs: number; type: "status"; data: RunStatusEvent }
  | { delayMs: number; type: "dag"; data: RunDagEvent }
  | { delayMs: number; type: "log"; data: { run_id: string; entry: RunLogEntry } }

function encodeDataUrl(label: string, content: string) {
  return `data:text/plain;charset=utf-8,${encodeURIComponent(
    `${label}\n\n${content}`,
  )}`
}

function matchPath(pattern: RegExp, path: string) {
  const match = pattern.exec(path)
  return match ? match.slice(1) : null
}

function nowStamp() {
  return new Date().toISOString()
}

const DEMO_LLM_PROVIDER_TEMPLATES: LlmProviderTemplate[] = [
  providerTemplate("openai", "OpenAI", "openai", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.openai.com/v1", [
    providerModelTemplate("gpt-5.4-mini", "GPT-5.4 Mini"),
    providerModelTemplate("gpt-5.4", "GPT-5.4"),
  ], ["chat_completions", "responses"]),
  providerTemplate("anthropic", "Anthropic", "anthropic", "anthropic_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.anthropic.com", [
    providerModelTemplate("claude-sonnet-4-6", "Claude Sonnet 4.6"),
  ]),
  providerTemplate("gemini", "Gemini", "gemini", "gemini_models", [
    providerField("api_key", "API key", true, true),
  ]),
  providerTemplate("grok", "Grok", "grok", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.x.ai/v1"),
  providerTemplate("groq", "Groq", "groq", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.groq.com/openai/v1"),
  providerTemplate("deepseek", "DeepSeek", "deepseek", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.deepseek.com/v1"),
  providerTemplate("openrouter", "OpenRouter", "openrouter", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://openrouter.ai/api/v1", [
    providerModelTemplate("openrouter/auto", "OpenRouter Auto"),
  ]),
  providerTemplate("kimi", "Kimi", "kimi", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.moonshot.cn/v1"),
  providerTemplate("qwen", "Qwen", "qwen", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://dashscope.aliyuncs.com/compatible-mode/v1"),
  providerTemplate("mistral", "Mistral", "mistral", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.mistral.ai/v1"),
  providerTemplate("cohere", "Cohere", "cohere", "cohere_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.cohere.ai/compatibility/v1"),
  providerTemplate("together", "Together AI", "together", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.together.xyz/v1"),
  providerTemplate("fireworks", "Fireworks AI", "fireworks", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.fireworks.ai/inference/v1"),
  providerTemplate("perplexity", "Perplexity", "perplexity", "openai_models", [
    providerField("api_key", "API key", true, true),
  ], "https://api.perplexity.ai"),
  providerTemplate("ollama", "Ollama", "ollama", "ollama_tags", [
    providerField("base_url", "Endpoint", false, true, "http://localhost:11434"),
    providerField("model_id", "Model ID", false, false),
  ], "http://localhost:11434"),
  providerTemplate("vllm", "vLLM", "vllm", "openai_models", [
    providerField("base_url", "Endpoint", false, true, "http://localhost:8000/v1"),
    providerField("api_key", "API key", true, false),
    providerField("model_id", "Model ID", false, false),
  ], "http://localhost:8000/v1"),
  providerTemplate("openai-compatible", "OpenAI Compatible", "openai_compatible", "openai_models", [
    providerField("base_url", "Endpoint", false, true, "https://api.example.com/v1"),
    providerField("api_key", "API key", true, false),
    providerField("model_id", "Model ID", false, false),
  ], "https://api.example.com/v1", [], ["chat_completions", "responses"]),
]

function providerTemplate(
  id: string,
  name: string,
  kind: LlmProviderKind,
  discovery: LlmProviderTemplate["discovery"],
  fields: LlmProviderTemplate["fields"],
  defaultBaseUrl: string | null = null,
  models: LlmProviderTemplate["models"] = [],
  supportedWireProtocols: LlmWireProtocol[] = ["chat_completions"],
): LlmProviderTemplate {
  return {
    id,
    name,
    kind,
    docs_url: `https://docs.example.com/${id}`,
    discovery,
    default_base_url: defaultBaseUrl,
    supported_wire_protocols: supportedWireProtocols,
    default_wire_protocol: "chat_completions",
    fields,
    models,
  }
}

function providerField(
  name: string,
  label: string,
  secret: boolean,
  required: boolean,
  defaultValue?: string,
): LlmProviderTemplate["fields"][number] {
  return {
    name,
    label,
    secret,
    required,
    placeholder: label,
    default: defaultValue,
  }
}

function providerModelTemplate(
  id: string,
  name: string,
): LlmProviderTemplate["models"][number] {
  return {
    id,
    name,
    context_length: 128000,
    max_output_tokens: 8192,
    supports_tools: true,
    supports_streaming: true,
    supports_vision: false,
    supports_json_schema: true,
    supports_reasoning: false,
  }
}

function templateApiKeyRequired(template: LlmProviderTemplate) {
  return Boolean(
    template.fields.find((field) => field.name === "api_key")?.required,
  )
}

function templateForProvider(provider: LlmProvider) {
  const templateId = String(provider.metadata?.providerTemplate ?? "")
  return (
    DEMO_LLM_PROVIDER_TEMPLATES.find((template) => template.id === templateId) ??
    DEMO_LLM_PROVIDER_TEMPLATES.find((template) => template.kind === provider.kind)
  )
}

function credentialForProvider(
  state: DemoRuntimeState,
  provider: LlmProvider,
): LlmProviderCredential {
  const existing = state.llmProviderCredentials[provider.id]
  if (existing) return existing
  const template = templateForProvider(provider)
  const requiresKey = template ? templateApiKeyRequired(template) : true
  return {
    provider_id: provider.id,
    source: "none",
    configured: false,
    available: !requiresKey,
    env_var_name: null,
    fingerprint: null,
    masked_hint: null,
    updated_at: null,
  }
}

function configuredProvider(
  state: DemoRuntimeState,
  provider: LlmProvider,
): LlmConfiguredProvider {
  return {
    ...provider,
    credential: credentialForProvider(state, provider),
  }
}

function llmConfiguration(state: DemoRuntimeState): LlmConfiguration {
  const providers = state.llmProviders.map((provider) =>
    configuredProvider(state, provider),
  )
  return {
    summary: {
      provider_count: providers.length,
      configured_provider_count: providers.filter(
        (provider) => provider.credential.configured,
      ).length,
      available_provider_count: providers.filter(
        (provider) => provider.credential.available,
      ).length,
      model_count: state.llmModels.length,
      profile_count: state.llmModelProfiles.length,
    },
    providers,
    models: clone(state.llmModels),
    profiles: clone(state.llmModelProfiles),
  }
}

function upsertDemoModel(
  state: DemoRuntimeState,
  providerId: string,
  modelId: string,
  displayName = modelId,
): LlmModel {
  const existing = state.llmModels.find(
    (model) => model.provider_id === providerId && model.model_id === modelId,
  )
  if (existing) {
    const updated = {
      ...existing,
      display_name: displayName,
      updated_at: nowStamp(),
    }
    state.llmModels = state.llmModels.map((model) =>
      model.id === existing.id ? updated : model,
    )
    return updated
  }

  const model: LlmModel = {
    id: `llm-model-demo-${String(state.llmModels.length + 1).padStart(3, "0")}`,
    provider_id: providerId,
    model_id: modelId,
    display_name: displayName,
    context_length: 128000,
    max_output_tokens: 8192,
    supports_tools: true,
    supports_streaming: true,
    supports_vision: false,
    supports_json_schema: true,
    supports_reasoning: /reason|r1|thinking|deepseek/i.test(modelId),
    default_temperature: null,
    default_top_p: null,
    cost_metadata: null,
    metadata: { demo: true },
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }
  state.llmModels = [model, ...state.llmModels]
  return model
}

function setDemoCredential(
  state: DemoRuntimeState,
  providerId: string,
  apiKey?: string | null,
  source: LlmProviderCredential["source"] = apiKey ? "stored" : "none",
) {
  const secret = apiKey?.trim() ?? ""
  state.llmProviderCredentials[providerId] = {
    provider_id: providerId,
    source,
    configured: source === "stored" || source === "env",
    available: source === "none" || Boolean(secret) || source === "env",
    env_var_name: source === "env" ? "DEMO_MODEL_KEY" : null,
    fingerprint: source === "stored" ? `fp_${providerId}` : null,
    masked_hint:
      source === "stored"
        ? maskDemoSecret(secret)
        : source === "env"
          ? "env:DEMO_MODEL_KEY"
          : null,
    updated_at: nowStamp(),
  }
}

function maskDemoSecret(secret: string) {
  if (!secret) return null
  if (secret.length <= 8) return "sk-..."
  return `${secret.slice(0, 3)}...${secret.slice(-4)}`
}

function setupDemoProvider(
  state: DemoRuntimeState,
  bodyJson: Record<string, unknown> | null,
): LlmProviderSetupResult {
  const templateId = String(bodyJson?.template_id ?? "").trim()
  const template = DEMO_LLM_PROVIDER_TEMPLATES.find(
    (candidate) => candidate.id === templateId,
  )
  if (!template) {
    throw new ApiError(`Unknown LLM provider template: ${templateId}`, {
      status: 400,
    })
  }

  const scope =
    typeof bodyJson?.scope === "string"
      ? (bodyJson.scope as LlmProviderScope)
      : "user"
  const providerId = typeof bodyJson?.provider_id === "string"
    ? bodyJson.provider_id
    : null
  const existing = providerId
    ? state.llmProviders.find((provider) => provider.id === providerId)
    : state.llmProviders.find(
        (provider) =>
          provider.scope === scope &&
          provider.metadata?.providerTemplate === template.id,
      )

  const baseUrl =
    typeof bodyJson?.base_url === "string" && bodyJson.base_url.trim()
      ? bodyJson.base_url.trim()
      : template.default_base_url ?? null
  const wireProtocol = readDemoWireProtocol(
    bodyJson?.wire_protocol,
    existing?.wire_protocol ?? template.default_wire_protocol,
  )
  const allowInsecureHttp =
    typeof bodyJson?.allow_insecure_http === "boolean"
      ? bodyJson.allow_insecure_http
      : existing?.allow_insecure_http ?? false
  const provider: LlmProvider = existing
    ? {
        ...existing,
        name:
          typeof bodyJson?.name === "string" && bodyJson.name.trim()
            ? bodyJson.name.trim()
            : existing.name || template.name,
        kind: template.kind,
        wire_protocol: wireProtocol,
        base_url: baseUrl,
        enabled: bodyJson?.enabled !== false,
        allow_insecure_http: allowInsecureHttp,
        metadata: {
          ...(existing.metadata ?? {}),
          providerTemplate: template.id,
        },
        updated_at: nowStamp(),
      }
    : {
        id: `llm-provider-demo-${String(state.llmProviderSequence).padStart(3, "0")}`,
        name:
          typeof bodyJson?.name === "string" && bodyJson.name.trim()
            ? bodyJson.name.trim()
            : template.name,
        kind: template.kind,
        wire_protocol: wireProtocol,
        base_url: baseUrl,
        api_key_ref: null,
        scope,
        workspace_id: "workspace-demo",
        user_id: scope === "user" ? "demo-user" : null,
        enabled: bodyJson?.enabled !== false,
        allow_insecure_http: allowInsecureHttp,
        test_status: null,
        metadata: { demo: true, providerTemplate: template.id },
        created_at: nowStamp(),
        updated_at: nowStamp(),
      }

  if (!existing) state.llmProviderSequence += 1
  state.llmProviders = existing
    ? state.llmProviders.map((item) => (item.id === provider.id ? provider : item))
    : [provider, ...state.llmProviders]

  const apiKey =
    typeof bodyJson?.api_key === "string" ? bodyJson.api_key.trim() : ""
  if (apiKey) {
    setDemoCredential(state, provider.id, apiKey, "stored")
  } else if (!state.llmProviderCredentials[provider.id] && !templateApiKeyRequired(template)) {
    setDemoCredential(state, provider.id, null, "none")
  }

  let setupModels = cleanDemoModelIds(bodyJson?.model_ids).map((modelId) =>
    upsertDemoModel(state, provider.id, modelId),
  )
  if (setupModels.length === 0 && template.models.length > 0) {
    setupModels = template.models.map((model) =>
      upsertDemoModel(state, provider.id, model.id, model.name),
    )
  }

  let discovered = false
  if (bodyJson?.discover === true) {
    discovered = true
    const discoveredModels =
      template.models.length > 0
        ? template.models
        : [providerModelTemplate(discoveryFallbackModelId(template), discoveryFallbackModelId(template))]
    setupModels = discoveredModels.map((model) =>
      upsertDemoModel(state, provider.id, model.id, model.name),
    )
  }

  return {
    provider: configuredProvider(state, provider),
    models: setupModels,
    discovered,
  }
}

function cleanDemoModelIds(value: unknown) {
  return Array.isArray(value)
    ? value
        .map((item) => String(item ?? "").trim())
        .filter(Boolean)
    : []
}

function readDemoWireProtocol(
  value: unknown,
  fallback: LlmWireProtocol = "chat_completions",
): LlmWireProtocol {
  return value === "responses" || value === "chat_completions"
    ? value
    : fallback
}

function discoveryFallbackModelId(template: LlmProviderTemplate) {
  if (template.id === "ollama") return "deepseek-r1:latest"
  if (template.id === "vllm") return "deepseek_v4"
  return `${template.id}-demo-model`
}

function listAgentCoreSessions(
  state: DemoRuntimeState,
  projectId?: string,
) {
  const sessions = projectId
    ? state.agentSessionsByProject.get(projectId) ?? []
    : [...state.agentSessionsByProject.values()].flat()

  return [...sessions]
    .filter((session) => session.status !== "deleted")
    .sort(
      (a, b) =>
        new Date(b.updated_at || b.created_at).getTime() -
        new Date(a.updated_at || a.created_at).getTime(),
    )
}

function findAgentCoreSession(
  state: DemoRuntimeState,
  sessionId: string,
) {
  for (const sessions of state.agentSessionsByProject.values()) {
    const match = sessions.find((session) => session.id === sessionId)
    if (match) return match
  }
  return null
}

function replaceAgentCoreSession(
  state: DemoRuntimeState,
  session: AgentCoreSession,
) {
  const current = state.agentSessionsByProject.get(session.project_id) ?? []
  const index = current.findIndex((item) => item.id === session.id)
  const next =
    index === -1
      ? [session, ...current]
      : current.map((item) => (item.id === session.id ? session : item))
  state.agentSessionsByProject.set(session.project_id, next)
}

function createAgentCoreSession(
  state: DemoRuntimeState,
  projectId: string,
  options?: {
    id?: string
    title?: string | null
    roleProfile?: string | null
    permissionMode?: AgentPermissionMode | null
    automationMode?: AgentAutomationMode | null
    defaultModelProfileId?: string | null
    metadata?: Record<string, unknown> | null
  },
) {
  const sessionId =
    options?.id ??
    `agent-session-demo-${String(state.agentSessionSequence).padStart(3, "0")}`
  if (!options?.id) state.agentSessionSequence += 1

  const session: AgentCoreSession = {
    id: sessionId,
    project_id: projectId,
    workspace_id: "workspace-demo",
    user_id: "demo-user",
    title: options?.title || "New demo analysis",
    role_profile: options?.roleProfile || "bioinformatics_engineer",
    permission_mode: options?.permissionMode || "guarded_auto",
    automation_mode: options?.automationMode || "assisted",
    default_model_profile_id: options?.defaultModelProfileId ?? null,
    status: "active",
    metadata: options?.metadata ?? { demo: true },
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }

  replaceAgentCoreSession(state, session)
  state.agentTurnsBySession.set(session.id, [])
  return session
}

function updateAgentCoreSession(
  state: DemoRuntimeState,
  sessionId: string,
  updates: {
    title?: string | null
    status?: AgentSessionStatus | null
    permissionMode?: AgentPermissionMode | null
    metadata?: Record<string, unknown> | null
  },
) {
  const existing = findAgentCoreSession(state, sessionId)
  if (!existing) throw new ApiError("Agent session not found", { status: 404 })
  const updated: AgentCoreSession = {
    ...existing,
    title:
      typeof updates.title === "string"
        ? updates.title.trim() || existing.title
        : existing.title,
    status: updates.status ?? existing.status,
    permission_mode: updates.permissionMode ?? existing.permission_mode,
    metadata:
      updates.metadata === undefined ? existing.metadata : updates.metadata,
    updated_at: nowStamp(),
  }
  replaceAgentCoreSession(state, updated)
  return updated
}

function deleteAgentCoreSession(
  state: DemoRuntimeState,
  sessionId: string,
) {
  const existing = findAgentCoreSession(state, sessionId)
  if (!existing) return
  state.agentSessionsByProject.set(
    existing.project_id,
    (state.agentSessionsByProject.get(existing.project_id) ?? []).filter(
      (session) => session.id !== sessionId,
    ),
  )
  const turns = state.agentTurnsBySession.get(sessionId) ?? []
  turns.forEach((turn) => {
    state.agentEventsByTurn.delete(turn.id)
    state.agentArtifactsByTurn.delete(turn.id)
  })
  for (const [actionId, action] of state.agentActions) {
    if (action.session_id === sessionId) state.agentActions.delete(actionId)
  }
  state.agentMemories = state.agentMemories.filter(
    (memory) => memory.session_id !== sessionId,
  )
  state.agentTurnsBySession.delete(sessionId)
}

function findAgentCoreTurn(state: DemoRuntimeState, turnId: string) {
  for (const turns of state.agentTurnsBySession.values()) {
    const turn = turns.find((item) => item.id === turnId)
    if (turn) return turn
  }
  return null
}

function replaceAgentCoreTurn(state: DemoRuntimeState, turn: AgentCoreTurn) {
  const turns = state.agentTurnsBySession.get(turn.session_id) ?? []
  state.agentTurnsBySession.set(
    turn.session_id,
    turns.map((item) => (item.id === turn.id ? turn : item)),
  )
}

function appendAgentCoreEvent(
  state: DemoRuntimeState,
  turn: AgentCoreTurn,
  type: string,
  payload: Record<string, unknown>,
  visibility: AgentCoreEvent["visibility"] = "user",
) {
  const current = state.agentEventsByTurn.get(turn.id) ?? []
  const event: AgentCoreEvent = {
    id: `agent-event-demo-${String(state.agentEventSequence).padStart(4, "0")}`,
    session_id: turn.session_id,
    turn_id: turn.id,
    seq: current.length + 1,
    type,
    payload,
    visibility,
    schema_version: 1,
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }
  state.agentEventSequence += 1
  state.agentEventsByTurn.set(turn.id, [...current, event])
  return event
}

function createAgentCoreTurn(
  state: DemoRuntimeState,
  sessionId: string,
  inputText: string,
  activeSkillNames: string[] = [],
) {
  const session = findAgentCoreSession(state, sessionId)
  if (!session) throw new ApiError("Agent session not found", { status: 404 })

  const now = nowStamp()
  const turnId = `agent-turn-demo-${String(state.agentTurnSequence).padStart(3, "0")}`
  state.agentTurnSequence += 1

  const runId = `run_demo_${String(state.runSequence).padStart(3, "0")}`
  state.runSequence += 1
  const run = createRunRecord(
    state,
    {
      project_id: session.project_id,
      workflow_id: "wf-rnaseq-quant-mini",
      values: {
        reads_r1: "deliveries/ecoli_R1.fastq.gz",
        reads_r2: "deliveries/ecoli_R2.fastq.gz",
        reference: "reference/ecoli_k12.fa",
      },
    },
    runId,
  )
  const artifacts = createRunArtifacts(runId)
  state.runs.set(runId, run)
  state.runLogs.set(runId, artifacts.logs)
  state.runOutputs.set(runId, artifacts.outputs)
  state.runDag.set(runId, artifacts.dag)
  state.runAudit.set(runId, artifacts.audit)

  const finalText =
    "I launched the seeded RNA-seq demo workflow. The live deck and runs view will update as the replay advances."

  const turn: AgentCoreTurn = {
    id: turnId,
    session_id: session.id,
    project_id: session.project_id,
    workspace_id: session.workspace_id,
    user_id: session.user_id,
    input_text: inputText,
    input_parts: [{ type: "text", text: inputText }],
    active_skill_names: activeSkillNames,
    status: "completed",
    model_profile_snapshot: {
      provider: "demo",
      model: "agent-core-demo",
    },
    final_text: finalText,
    token_usage: {
      input_tokens: 512,
      output_tokens: 178,
      context_tokens: 1024,
    },
    error_code: null,
    error_message: null,
    created_at: now,
    updated_at: now,
    started_at: now,
    completed_at: nowStamp(),
  }

  const actionId = `agent-action-demo-${String(state.agentActionSequence).padStart(3, "0")}`
  state.agentActionSequence += 1
  const action: AgentCoreAction = {
    id: actionId,
    session_id: session.id,
    turn_id: turn.id,
    parent_action_id: null,
    kind: "run",
    name: "runs.submit",
    input: {
      run_id: runId,
      workflow_id: run.workflow_id,
    },
    input_preview: `Submit ${run.workflow_id ?? "workflow"} with paired FASTQ inputs.`,
    redacted_input: null,
    risk_level: "act_low",
    risk_reasons: [],
    read_scope: [{ kind: "project", id: session.project_id }],
    write_scope: [{ kind: "run", id: runId }],
    affected_resources: [{ kind: "run", id: runId }],
    permission_decision: null,
    status: "waiting_decision",
    result: null,
    error: null,
    audit_summary: "Demo run submission is waiting for an AgentCore action decision.",
    rollback_hint: "Cancel the demo run if this action should not continue.",
    artifact_policy: { register_run_ref: true },
    created_at: now,
    updated_at: now,
    started_at: null,
    completed_at: null,
  }
  state.agentActions.set(action.id, action)

  const agentArtifact: AgentCoreArtifact = {
    id: `agent-artifact-demo-${String(state.agentArtifactSequence).padStart(3, "0")}`,
    session_id: session.id,
    turn_id: turn.id,
    action_id: action.id,
    type: "run_ref",
    title: "Seeded RNA-seq demo run",
    summary: `Registered demo run ${runId} for the RNA-seq workflow.`,
    payload: {
      run_id: runId,
      workflow_id: run.workflow_id,
      status: run.status,
    },
    file_path: null,
    resource_ref: {
      kind: "run",
      id: runId,
    },
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }
  state.agentArtifactSequence += 1
  state.agentArtifactsByTurn.set(turn.id, [agentArtifact])

  const memory: AgentCoreMemory = {
    id: `agent-memory-demo-${String(state.agentMemorySequence).padStart(3, "0")}`,
    workspace_id: session.workspace_id,
    project_id: session.project_id,
    session_id: session.id,
    scope: "run",
    type: "run_lesson",
    content: {
      workflow_id: run.workflow_id,
      reference_genome: "ecoli_k12",
      lesson: "Seeded demo run uses paired FASTQ inputs and a local reference FASTA.",
    },
    source: {
      turn_id: turn.id,
      run_id: runId,
    },
    confidence: 88,
    status: "proposed",
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }
  state.agentMemorySequence += 1
  state.agentMemories = [memory, ...state.agentMemories]

  const existingTurns = state.agentTurnsBySession.get(session.id) ?? []
  state.agentTurnsBySession.set(session.id, [...existingTurns, turn])
  replaceAgentCoreSession(state, {
    ...session,
    title: session.title || "RNA-seq demo run",
    updated_at: nowStamp(),
  })

  appendAgentCoreEvent(state, turn, "turn.created", {
    input_text: inputText,
  })
  appendAgentCoreEvent(state, turn, "turn.started", {})
  appendAgentCoreEvent(state, turn, "assistant.thinking.summary", {
    text: "Demo runtime selected the seeded RNA-seq workflow and prepared a run submission.",
  })
  appendAgentCoreEvent(state, turn, "user_input.requested", {
    request_id: `agent-question-demo-${turn.id}`,
    question: "Which reference should be used for this demo run?",
    reason: "Reference choice controls alignment, annotation, and downstream QC interpretation.",
    options: ["ecoli_k12", "hg38"],
  })
  appendAgentCoreEvent(state, turn, "user_input.resolved", {
    request_id: `agent-question-demo-${turn.id}`,
    answer: "ecoli_k12",
  })
  appendAgentCoreEvent(state, turn, "action.requested", {
    action_id: action.id,
    kind: "run",
    name: "runs.submit",
    run_id: runId,
    risk_level: "act_low",
    input_preview: action.input_preview,
  })
  appendAgentCoreEvent(state, turn, "action.waiting_decision", {
    action_id: action.id,
    kind: "run",
    name: "runs.submit",
    run_id: runId,
    risk_level: "act_low",
    input_preview: action.input_preview,
  })
  appendAgentCoreEvent(state, turn, "action.completed", {
    action_id: action.id,
    kind: "run",
    name: "runs.submit",
    run_id: runId,
    status: "submitted",
  })
  appendAgentCoreEvent(state, turn, "artifact.created", {
    artifact_id: agentArtifact.id,
    type: "run_ref",
    title: "Seeded RNA-seq demo run",
    resource_ref: {
      kind: "run",
      id: runId,
    },
  })
  appendAgentCoreEvent(state, turn, "memory.proposed", {
    memory_id: memory.id,
    scope: memory.scope,
    type: memory.type,
  })
  appendAgentCoreEvent(state, turn, "assistant.text.completed", {
    text: finalText,
  })
  appendAgentCoreEvent(state, turn, "turn.completed", {
    final_text: finalText,
  })

  scheduleRunReplay(
    state,
    session.project_id,
    runId,
    buildRunReplay(runId),
    0,
  )

  return turn
}

function emitEnvelope<T>(
  state: DemoRuntimeState,
  eventName: string,
  projectId: string,
  data: T,
  options?: {
    runId?: string
    imageId?: string
  },
) {
  const envelope: EventEnvelope<T> = {
    id: `evt-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    event: eventName,
    project_id: projectId,
    timestamp: nowStamp(),
    data,
    run_id: options?.runId,
    image_id: options?.imageId,
  }

  for (const [, subscriber] of state.subscribers) {
    if (subscriber.projectId && subscriber.projectId !== projectId) continue
    if (subscriber.runId && subscriber.runId !== envelope.run_id) continue
    if (subscriber.imageId && subscriber.imageId !== envelope.image_id) continue

    if (eventName === "run.status") {
      subscriber.onRunStatus?.(envelope as EventEnvelope<RunStatusEvent>)
    } else if (eventName === "run.log") {
      subscriber.onRunLog?.(envelope as EventEnvelope<{ run_id: string; entry: RunLogEntry }>)
    } else if (eventName === "run.dag") {
      subscriber.onRunDag?.(envelope as EventEnvelope<RunDagEvent>)
    } else if (eventName === "image.progress") {
      subscriber.onImageProgress?.(
        envelope as EventEnvelope<{
          image_id: string
          progress?: number | null
          status: DockerImage["status"]
        }>,
      )
    }
  }
}

function applyRunReplayStep(
  state: DemoRuntimeState,
  projectId: string,
  runId: string,
  step: DemoRunReplayStep,
) {
  if (step.type === "status") {
    const current = state.runs.get(runId)
    if (!current) return
    const completed = step.data.status === "completed"
    const updated: Run = {
      ...current,
      status: step.data.status,
      current_task: step.data.current_task ?? null,
      tasks_completed: step.data.tasks_completed ?? current.tasks_completed,
      tasks_total: step.data.tasks_total ?? current.tasks_total,
      completed_at: completed ? nowStamp() : current.completed_at,
      duration_seconds: completed ? 96 : current.duration_seconds,
      updated_at: nowStamp(),
    }
    state.runs.set(runId, updated)
    emitEnvelope(state, "run.status", projectId, step.data, {
      runId,
    })
    return
  }

  if (step.type === "dag") {
    state.runDag.set(runId, clone(step.data.dag))
    emitEnvelope(state, "run.dag", projectId, step.data, {
      runId,
    })
    return
  }

  const logs = state.runLogs.get(runId) ?? { logs: [] }
  logs.logs = [...logs.logs, step.data.entry]
  state.runLogs.set(runId, logs)
  emitEnvelope(
    state,
    "run.log",
    projectId,
    {
      run_id: runId,
      message: step.data.entry.message,
      level: step.data.entry.level,
      task: step.data.entry.task,
      timestamp: step.data.entry.timestamp,
    },
    { runId },
  )
}

function scheduleRunReplay(
  state: DemoRuntimeState,
  projectId: string,
  runId: string,
  replay: DemoRunReplayStep[],
  initialDelayMs = 0,
) {
  let elapsed = initialDelayMs
  replay.forEach((step) => {
    elapsed += step.delayMs
    setTimeout(() => {
      applyRunReplayStep(state, projectId, runId, step)
    }, elapsed)
  })
  return elapsed
}

function createRunningDag(): DagData {
  return {
    nodes: [
      {
        id: "reads_stats",
        type: "pipeline",
        position: { x: 250, y: 50 },
        data: {
          label: "READS_STATS",
          status: "running",
          displayLabel: "Read Quality Stats",
        },
      },
      {
        id: "reference_stats",
        type: "pipeline",
        position: { x: 250, y: 200 },
        data: {
          label: "REFERENCE_STATS",
          status: "pending",
          displayLabel: "Reference Alignment",
        },
      },
      {
        id: "summary_report",
        type: "pipeline",
        position: { x: 250, y: 350 },
        data: {
          label: "SUMMARY_REPORT",
          status: "pending",
          displayLabel: "Summary Report",
        },
      },
    ],
    edges: [
      { id: "e1", source: "reads_stats", target: "reference_stats", animated: true },
      { id: "e2", source: "reference_stats", target: "summary_report", animated: false },
    ],
  }
}

function createCompletedDag(): DagData {
  return {
    nodes: [
      {
        id: "reads_stats",
        type: "pipeline",
        position: { x: 250, y: 50 },
        data: {
          label: "READS_STATS",
          status: "success",
          displayLabel: "Read Quality Stats",
          duration: 124,
        },
      },
      {
        id: "reference_stats",
        type: "pipeline",
        position: { x: 250, y: 200 },
        data: {
          label: "REFERENCE_STATS",
          status: "success",
          displayLabel: "Reference Alignment",
          duration: 188,
        },
      },
      {
        id: "summary_report",
        type: "pipeline",
        position: { x: 250, y: 350 },
        data: {
          label: "SUMMARY_REPORT",
          status: "success",
          displayLabel: "Summary Report",
          duration: 96,
        },
      },
    ],
    edges: [
      { id: "e1", source: "reads_stats", target: "reference_stats", animated: false },
      { id: "e2", source: "reference_stats", target: "summary_report", animated: false },
    ],
  }
}

function buildRunReplay(runId: string): DemoRunReplayStep[] {
  return [
    {
      delayMs: 80,
      type: "status",
      data: {
        run_id: runId,
        status: "queued",
        current_task: "Queueing",
        tasks_completed: 0,
        tasks_total: 3,
      },
    },
    {
      delayMs: 200,
      type: "status",
      data: {
        run_id: runId,
        status: "running",
        current_task: "READS_STATS",
        tasks_completed: 0,
        tasks_total: 3,
      },
    },
    {
      delayMs: 220,
      type: "dag",
      data: { run_id: runId, dag: createRunningDag() },
    },
    {
      delayMs: 240,
      type: "log",
      data: {
        run_id: runId,
        entry: {
          message: "Initializing reads quality checks",
          task: "READS_STATS",
          level: "info",
          timestamp: nowStamp(),
        },
      },
    },
    {
      delayMs: 520,
      type: "log",
      data: {
        run_id: runId,
        entry: {
          message: "Reference alignment metrics look healthy",
          task: "REFERENCE_STATS",
          level: "info",
          timestamp: nowStamp(),
        },
      },
    },
    {
      delayMs: 800,
      type: "status",
      data: {
        run_id: runId,
        status: "completed",
        current_task: null,
        tasks_completed: 3,
        tasks_total: 3,
      },
    },
    {
      delayMs: 820,
      type: "dag",
      data: {
        run_id: runId,
        dag: createCompletedDag(),
      },
    },
    {
      delayMs: 860,
      type: "log",
      data: {
        run_id: runId,
        entry: {
          message: "Demo summary report written to reports/summary.md",
          task: "SUMMARY_REPORT",
          level: "info",
          timestamp: nowStamp(),
        },
      },
    },
  ]
}

function syncImageStats(state: DemoRuntimeState) {
  const local = state.images.filter((image) => image.status === "local").length
  const remote = state.images.filter((image) => image.status === "remote").length
  const pulling = state.images.filter((image) => image.status === "pulling").length

  state.scenario.dashboard.stats.images = {
    total: state.images.length,
    local,
    remote,
    pulling,
  }
  state.imageStatus.last_synced_at = nowStamp()
}

function inferRegistry(name: string) {
  const firstSegment = name.split("/")[0] ?? ""
  if (firstSegment.includes(".") || firstSegment.includes(":") || firstSegment === "localhost") {
    return firstSegment
  }
  return "docker.io"
}

function upsertImage(state: DemoRuntimeState, image: DockerImage) {
  const existingIndex = state.images.findIndex(
    (candidate) => candidate.full_name === image.full_name,
  )
  if (existingIndex === -1) {
    state.images = [image, ...state.images]
  } else {
    const next = [...state.images]
    next[existingIndex] = image
    state.images = next
  }
  syncImageStats(state)
}

function createDemoImage(
  state: DemoRuntimeState,
  name: string,
  tag: string,
  status: DockerImage["status"],
  description: string,
) {
  const imageId = `img-demo-${String(state.imageSequence).padStart(3, "0")}`
  state.imageSequence += 1
  const registry = inferRegistry(name)

  return {
    id: imageId,
    name,
    tag,
    full_name: `${name}:${tag}`,
    description,
    size_bytes: 186_646_528,
    status,
    registry,
    pull_progress: status === "pulling" ? 58 : null,
    error_message: null,
    labels: {
      maintainer: "Bioinfoflow",
      demo: "true",
    },
    env: ["BIOINFOFLOW_DEMO=1", "PATH=/usr/local/bin:/usr/bin"],
    entrypoint: ["/bin/bash"],
    created_at: nowStamp(),
    updated_at: nowStamp(),
  } satisfies DockerImage
}

function getProjectRuns(state: DemoRuntimeState, projectId?: string | null) {
  const runs = Array.from(state.runs.values())
    .sort((left, right) => right.run_id.localeCompare(left.run_id))
  if (!projectId) return runs
  return runs.filter((run) => run.project_id === projectId)
}

function findFileNode(nodes: DemoFileNode[], path: string): DemoFileNode | null {
  for (const node of nodes) {
    if (node.path === path) return node
    if (node.type === "directory") {
      const nested = findFileNode(node.children, path)
      if (nested) return nested
    }
  }
  return null
}

function listChildren(nodes: DemoFileNode[], path: string) {
  if (!path || path === ".") {
    return nodes.map((node) => {
      if (node.type === "directory") {
        return {
          name: node.name,
          type: node.type,
          path: node.path,
          size_bytes: null,
        }
      }
      return {
        name: node.name,
        type: node.type,
        path: node.path,
        size_bytes: node.size_bytes ?? null,
      }
    })
  }

  const node = findFileNode(nodes, path)
  if (!node || node.type !== "directory") return []
  return node.children.map((child) => {
    if (child.type === "directory") {
      return {
        name: child.name,
        type: child.type,
        path: child.path,
        size_bytes: null,
      }
    }
    return {
      name: child.name,
      type: child.type,
      path: child.path,
      size_bytes: child.size_bytes ?? null,
    }
  })
}

function createRunRecord(
  state: DemoRuntimeState,
  payload: RunCreateV2,
  runId: string,
): Run {
  return {
    id: `run-model-${runId}`,
    run_id: runId,
    project_id: payload.project_id,
    workflow_id: payload.workflow_id,
    status: "pending",
    config: payload.values,
    started_at: nowStamp(),
    completed_at: null,
    duration_seconds: null,
    samples_count: 2,
    tasks_total: 3,
    tasks_completed: 0,
    current_task: "Queued",
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }
}

function createRunArtifacts(runId: string) {
  return {
    logs: {
      logs: [] as RunLogEntry[],
    },
    outputs: {
      files: [
        {
          name: "summary.md",
          path: "reports/summary.md",
          size_bytes: 812,
          type: "file" as const,
        },
        {
          name: "counts.tsv",
          path: "counts/counts.tsv",
          size_bytes: 428,
          type: "file" as const,
        },
        {
          name: "metrics.json",
          path: "reports/metrics.json",
          size_bytes: 264,
          type: "file" as const,
        },
      ],
    },
    dag: createRunningDag(),
    audit: [
      {
        id: `audit-${runId}-submitted`,
        run_id: runId,
        action: "run.submitted",
        actor: "Demo Runtime",
        details: { origin: "demo", run_id: runId },
        created_at: nowStamp(),
      },
    ] as AuditLogEntry[],
  }
}

function createWorkflowRecord(
  state: DemoRuntimeState,
  payload: Record<string, unknown>,
  options?: {
    name?: string
    sourceRef?: string | null
    entrypointRelpath?: string | null
  },
): Workflow {
  const workflowId = `wf-demo-${String(state.workflowSequence).padStart(3, "0")}`
  state.workflowSequence += 1
  const source = (payload.source as Workflow["source"]) || "local"
  const engine = (payload.engine as Workflow["engine"]) || "nextflow"
  const name =
    options?.name ??
    String(
      payload.name ??
        payload.file_name ??
        payload.source_ref ??
        `demo-workflow-${state.workflowSequence - 1}`,
    )
      .replace(/^nf-core\//, "")
      .replace(/\.(wdl|nf)$/i, "")

  const workflow: Workflow = {
    id: workflowId,
    name,
    description:
      typeof payload.description === "string" && payload.description.trim()
        ? payload.description.trim()
        : "Registered in the demo runtime.",
    source,
    engine,
    source_ref:
      options?.sourceRef ??
      (typeof payload.source_ref === "string" ? payload.source_ref : null),
    entrypoint_relpath: options?.entrypointRelpath ?? null,
    version:
      typeof payload.version === "string" && payload.version.trim()
        ? payload.version.trim()
        : "1.0.0",
    created_at: nowStamp(),
    updated_at: nowStamp(),
  }

  state.scenario.workflows = [workflow, ...state.scenario.workflows]
  state.scenario.workflowDag[workflowId] = clone(createRunningDag())
  state.scenario.workflowSource[workflowId] =
    typeof payload.content === "string" && payload.content.trim()
      ? payload.content
      : `// Demo workflow source for ${name}\nworkflow { main: true }`
  state.scenario.formSpecs[workflowId] = clone(
    state.scenario.formSpecs["wf-rnaseq-quant-mini"],
  )

  return workflow
}

async function readUploadedFile(body: FormData | null, fallbackName: string) {
  const file = body?.get("file")
  if (!file || typeof File === "undefined" || !(file instanceof File)) {
    return {
      name: fallbackName,
      content: "Demo uploaded file",
      size: null as number | null,
    }
  }

  return {
    name: file.name || fallbackName,
    content: await file.text(),
    size: file.size || null,
  }
}

function upsertWorkspaceFile(
  state: DemoRuntimeState,
  projectId: string,
  path: string,
  content: string,
  sizeBytes: number | null,
) {
  const rootNodes = clone(state.workspaceFiles.get(projectId) ?? [])
  const [topLevel, ...rest] = path.split("/")
  if (!topLevel || rest.length === 0) return

  let directory = rootNodes.find(
    (node): node is Extract<DemoFileNode, { type: "directory" }> =>
      node.type === "directory" && node.path === topLevel,
  )

  if (!directory) {
    directory = {
      name: topLevel,
      type: "directory",
      path: topLevel,
      children: [],
    }
    rootNodes.unshift(directory)
  }

  directory.children = directory.children.filter((child) => child.path !== path)
  directory.children.unshift({
    name: rest.at(-1) ?? path,
    type: "file",
    path,
    content,
    size_bytes: sizeBytes,
  })

  state.workspaceFiles.set(projectId, rootNodes)
}

function createDemoRuntimeInternal(): AppRuntime {
  const state = createInitialState()

  const request = async <T>(
    path: string,
    options: RuntimeRequestOptions = {},
  ): Promise<RuntimeRequestResult<T>> => {
    const method = (options.method || "GET").toUpperCase()
    const params = options.params ?? {}
    const bodyText =
      typeof options.body === "string" ? options.body : null
    const bodyJson = bodyText ? JSON.parse(bodyText) : null
    const bodyFormData =
      typeof FormData !== "undefined" && options.body instanceof FormData
        ? options.body
        : null

    if (path === "/projects" && method === "GET") {
      return { data: clone(state.scenario.projects) as T }
    }

    if (path === "/projects" && method === "POST") {
      const projectId = `project-demo-${String(state.projectSequence).padStart(3, "0")}`
      state.projectSequence += 1
      const project: Project = {
        id: projectId,
        name:
          typeof bodyJson?.name === "string" && bodyJson.name.trim()
            ? bodyJson.name.trim()
            : `Demo Project ${state.projectSequence - 1}`,
        description:
          typeof bodyJson?.description === "string"
            ? bodyJson.description.trim() || null
            : null,
        created_at: nowStamp(),
        updated_at: nowStamp(),
      }
      state.scenario.projects = [project, ...state.scenario.projects]
      state.workflowGroupsByProject.set(projectId, [])
      state.workspaceFiles.set(projectId, [])
      state.agentSessionsByProject.set(projectId, [])
      return { data: clone(project) as T }
    }

    if (path === "/projects/default" && method === "GET") {
      throw new ApiError("Default project unavailable", { status: 404 })
    }

    const projectMatch = matchPath(/^\/projects\/([^/]+)$/, path)
    if (projectMatch && method === "PATCH") {
      const [projectId] = projectMatch
      const project = state.scenario.projects.find((item) => item.id === projectId)
      if (!project) throw new ApiError("Project not found", { status: 404 })
      if (typeof bodyJson?.name === "string" && bodyJson.name.trim()) {
        project.name = bodyJson.name.trim()
      }
      if (typeof bodyJson?.description === "string") {
        project.description = bodyJson.description.trim() || null
      }
      project.updated_at = nowStamp()
      return { data: clone(project) as T }
    }

    if (projectMatch && method === "DELETE") {
      const [projectId] = projectMatch
      state.scenario.projects = state.scenario.projects.filter(
        (item) => item.id !== projectId,
      )
      state.workflowGroupsByProject.delete(projectId)
      state.workspaceFiles.delete(projectId)
      const sessions = state.agentSessionsByProject.get(projectId) ?? []
      sessions.forEach((session) => {
        const turns = state.agentTurnsBySession.get(session.id) ?? []
        turns.forEach((turn) => state.agentEventsByTurn.delete(turn.id))
        state.agentTurnsBySession.delete(session.id)
      })
      state.agentSessionsByProject.delete(projectId)
      return { data: null as T }
    }

    const projectRunsMatch = matchPath(/^\/projects\/([^/]+)\/workflows$/, path)
    if (projectRunsMatch && method === "GET") {
      const [projectId] = projectRunsMatch
      return {
        data: clone(state.workflowGroupsByProject.get(projectId) ?? []) as T,
      }
    }

    const bindWorkflowMatch = matchPath(
      /^\/projects\/([^/]+)\/workflows\/([^/]+):bind$/,
      path,
    )
    if (bindWorkflowMatch && method === "POST") {
      const [projectId, workflowId] = bindWorkflowMatch
      const workflow = state.scenario.workflows.find((item) => item.id === workflowId)
      if (!workflow) throw new ApiError("Workflow not found", { status: 404 })
      const current = state.workflowGroupsByProject.get(projectId) ?? []
      if (!current.some((group) => group.pinned_workflow.id === workflowId)) {
        current.unshift({
          source: workflow.source,
          name: workflow.name,
          pinned_workflow: workflow,
          versions: [workflow],
        })
      }
      state.workflowGroupsByProject.set(projectId, current)
      return { data: null as T }
    }

    const unbindWorkflowMatch = matchPath(
      /^\/projects\/([^/]+)\/workflows\/([^/]+):unbind$/,
      path,
    )
    if (unbindWorkflowMatch && method === "DELETE") {
      const [projectId, workflowId] = unbindWorkflowMatch
      const current = state.workflowGroupsByProject.get(projectId) ?? []
      state.workflowGroupsByProject.set(
        projectId,
        current.filter((group) => group.pinned_workflow.id !== workflowId),
      )
      return { data: null as T }
    }

    const pinsMatch = matchPath(/^\/projects\/([^/]+)\/workflow-pins$/, path)
    if (pinsMatch && method === "POST") {
      return { data: null as T }
    }

    if (path === "/workflows" && method === "GET") {
      return { data: clone(state.scenario.workflows) as T }
    }

    if (path === "/workflows" && method === "POST") {
      const workflow = createWorkflowRecord(state, bodyJson ?? {})
      return { data: clone(workflow) as T }
    }

    const workflowMatch = matchPath(/^\/workflows\/([^/]+)$/, path)
    if (workflowMatch && method === "GET") {
      const [workflowId] = workflowMatch
      const workflow = state.scenario.workflows.find((item) => item.id === workflowId)
      if (!workflow) throw new ApiError("Workflow not found", { status: 404 })
      return { data: clone(workflow) as T }
    }
    if (workflowMatch && method === "DELETE") {
      return { data: null as T }
    }

    const workflowDagMatch = matchPath(/^\/workflows\/([^/]+)\/dag$/, path)
    if (workflowDagMatch && method === "GET") {
      const [workflowId] = workflowDagMatch
      return {
        data: clone(state.scenario.workflowDag[workflowId]) as T,
      }
    }

    const workflowSourceMatch = matchPath(/^\/workflows\/([^/]+)\/source$/, path)
    if (workflowSourceMatch && method === "GET") {
      const [workflowId] = workflowSourceMatch
      return {
        data: { content: state.scenario.workflowSource[workflowId] ?? "" } as T,
      }
    }

    const formSpecMatch = matchPath(/^\/workflows\/([^/]+)\/form-spec$/, path)
    if (formSpecMatch && method === "GET") {
      const [workflowId] = formSpecMatch
      const spec = state.scenario.formSpecs[workflowId]
      if (!spec) throw new ApiError("Workflow form spec not found", { status: 404 })
      return { data: clone(spec) as T }
    }

    if (path === "/workflows/validate" && method === "POST") {
      const response: ValidateWorkflowResponse = {
        valid: true,
        errors: [],
        warnings: [],
        schema: state.scenario.workflows[0]?.schema_json ?? null,
        dag: clone(createRunningDag()),
      }
      return { data: response as T }
    }

    if (path === "/workflows/local-bundle" && method === "POST") {
      const workflow = createWorkflowRecord(
        state,
        {
          source: "local",
          engine: bodyFormData?.get("engine") ?? "nextflow",
          name: bodyFormData?.get("name") ?? null,
          version: bodyFormData?.get("version") ?? null,
          description: bodyFormData?.get("description") ?? null,
        },
        {
          name:
            typeof bodyFormData?.get("name") === "string"
              ? String(bodyFormData?.get("name"))
              : "demo-bundle",
          entrypointRelpath:
            typeof bodyFormData?.get("entrypoint_relpath") === "string"
              ? String(bodyFormData?.get("entrypoint_relpath"))
              : null,
        },
      )
      return { data: clone(workflow) as T }
    }

    if (path === "/runs" && method === "GET") {
      const runs = getProjectRuns(
        state,
        typeof params.project_id === "string" ? params.project_id : null,
      )
      return {
        data: clone(runs) as T,
        meta: {
          pagination: {
            limit:
              typeof params.limit === "number"
                ? params.limit
                : Number(params.limit) || runs.length,
            total_count: runs.length,
            has_more: false,
            next_cursor: null,
          },
        },
      }
    }

    if (path === "/runs" && method === "POST") {
      const payload = bodyJson as RunCreateV2
      const runId = `run_demo_${String(state.runSequence).padStart(3, "0")}`
      state.runSequence += 1
      const run = createRunRecord(state, payload, runId)
      const artifacts = createRunArtifacts(runId)
      state.runs.set(runId, run)
      state.runLogs.set(runId, artifacts.logs)
      state.runOutputs.set(runId, artifacts.outputs)
      state.runDag.set(runId, artifacts.dag)
      state.runAudit.set(runId, artifacts.audit)

      scheduleRunReplay(state, payload.project_id, runId, buildRunReplay(runId))

      return { data: { run_id: runId } as T }
    }

    const runMatch = matchPath(/^\/runs\/([^/]+)$/, path)
    if (runMatch && method === "GET") {
      const [runId] = runMatch
      const run = state.runs.get(runId)
      if (!run) throw new ApiError("Run not found", { status: 404 })
      return { data: clone(run) as T }
    }
    if (runMatch && method === "DELETE") {
      return { data: null as T }
    }

    const runStatusActionMatch = matchPath(/^\/runs\/([^/]+)\/(retry|resume|cancel|cleanup)$/, path)
    if (runStatusActionMatch && method === "POST") {
      const [runId, action] = runStatusActionMatch
      const run = state.runs.get(runId)
      if (!run) throw new ApiError("Run not found", { status: 404 })
      if (action === "cancel") {
        const updated = {
          ...run,
          status: "cancelled" as const,
          updated_at: nowStamp(),
        }
        state.runs.set(runId, updated)
        return { data: clone(updated) as T }
      }
      return { data: clone(run) as T }
    }

    const runLogsMatch = matchPath(/^\/runs\/([^/]+)\/logs$/, path)
    if (runLogsMatch && method === "GET") {
      const [runId] = runLogsMatch
      return {
        data: clone(state.runLogs.get(runId) ?? { logs: [] }) as T,
      }
    }

    const runOutputsMatch = matchPath(/^\/runs\/([^/]+)\/outputs$/, path)
    if (runOutputsMatch && method === "GET") {
      const [runId] = runOutputsMatch
      return {
        data: clone(state.runOutputs.get(runId) ?? { files: [] }) as T,
      }
    }

    const runDagMatch = matchPath(/^\/runs\/([^/]+)\/dag$/, path)
    if (runDagMatch && method === "GET") {
      const [runId] = runDagMatch
      return {
        data: clone(state.runDag.get(runId) ?? createRunningDag()) as T,
      }
    }

    const runAuditMatch = matchPath(/^\/runs\/([^/]+)\/audit$/, path)
    if (runAuditMatch && method === "GET") {
      const [runId] = runAuditMatch
      return {
        data: clone(state.runAudit.get(runId) ?? []) as T,
      }
    }

    if (path === "/stats" && method === "GET") {
      const runs = Array.from(state.runs.values())
      const completed = runs.filter((run) => run.status === "completed").length
      const running = runs.filter((run) => run.status === "running").length
      const queued = runs.filter((run) => run.status === "queued").length
      const pending = runs.filter((run) => run.status === "pending").length
      const failed = runs.filter((run) => run.status === "failed").length
      const cancelled = runs.filter((run) => run.status === "cancelled").length
      return {
        data: {
          ...clone(state.scenario.dashboard.stats),
          runs: {
            total: runs.length,
            completed,
            running,
            queued,
            pending,
            failed,
            cancelled,
          },
          recent_runs: runs.slice(0, 5).map((run) => ({
            run_id: run.run_id,
            workflow_id: run.workflow_id ?? null,
            status: run.status,
            started_at: run.started_at ?? null,
            duration_seconds: run.duration_seconds ?? null,
            current_task: run.current_task ?? null,
          })),
        } as T,
      }
    }

    if (path === "/system/health" && method === "GET") {
      return { data: clone(state.scenario.dashboard.health) as T }
    }

    if (path === "/system/gpu" && method === "GET") {
      return { data: clone(state.scenario.dashboard.gpu) as T }
    }

    if (path === "/scheduler/status" && method === "GET") {
      return { data: clone(state.scenario.dashboard.scheduler) as T }
    }

    if (path === "/agent/skills" && method === "GET") {
      return { data: { skills: clone(DEMO_AGENT_SKILLS) } as T }
    }

    if (path === "/agent/sessions" && method === "GET") {
      const projectId =
        typeof params.project_id === "string" ? params.project_id : undefined
      return {
        data: clone(listAgentCoreSessions(state, projectId)) as T,
      }
    }

    if (path === "/agent/toolsets" && method === "GET") {
      return {
        data: {
          toolsets: [
            {
              name: "default",
              tools: ["projects.list", "workflows.list", "runs.list", "runs.logs"],
            },
            {
              name: "execution",
              tools: [
                "projects.list",
                "workflows.list",
                "runs.list",
                "runs.logs",
                "execution.shell",
              ],
            },
          ],
        } as T,
      }
    }

    if (path === "/agent/sessions" && method === "POST") {
      const projectId =
        typeof bodyJson?.project_id === "string" && bodyJson.project_id
          ? bodyJson.project_id
          : state.scenario.contextDefaults.selectedProjectId
      const session = createAgentCoreSession(state, projectId, {
        title:
          typeof bodyJson?.title === "string" ? bodyJson.title : undefined,
        roleProfile:
          typeof bodyJson?.role_profile === "string"
            ? bodyJson.role_profile
            : undefined,
        permissionMode:
          typeof bodyJson?.permission_mode === "string"
            ? (bodyJson.permission_mode as AgentPermissionMode)
            : undefined,
        automationMode:
          typeof bodyJson?.automation_mode === "string"
            ? (bodyJson.automation_mode as AgentAutomationMode)
            : undefined,
        defaultModelProfileId:
          typeof bodyJson?.default_model_profile_id === "string"
            ? bodyJson.default_model_profile_id
            : null,
        metadata:
          bodyJson?.metadata && typeof bodyJson.metadata === "object"
            ? (bodyJson.metadata as Record<string, unknown>)
            : undefined,
      })
      return { data: clone(session) as T }
    }

    const agentSessionMatch = matchPath(/^\/agent\/sessions\/([^/]+)$/, path)
    if (agentSessionMatch && method === "GET") {
      const [sessionId] = agentSessionMatch
      const session = findAgentCoreSession(state, sessionId)
      if (!session) throw new ApiError("Agent session not found", { status: 404 })
      return { data: clone(session) as T }
    }

    if (agentSessionMatch && method === "PATCH") {
      const [sessionId] = agentSessionMatch
      const session = updateAgentCoreSession(state, sessionId, {
        title: typeof bodyJson?.title === "string" ? bodyJson.title : undefined,
        status:
          typeof bodyJson?.status === "string"
            ? (bodyJson.status as AgentSessionStatus)
            : undefined,
        permissionMode:
          typeof bodyJson?.permission_mode === "string"
            ? (bodyJson.permission_mode as AgentPermissionMode)
            : undefined,
        metadata:
          bodyJson && Object.hasOwn(bodyJson, "metadata")
            ? (bodyJson.metadata as Record<string, unknown> | null)
            : undefined,
      })
      return { data: clone(session) as T }
    }

    if (agentSessionMatch && method === "DELETE") {
      const [sessionId] = agentSessionMatch
      deleteAgentCoreSession(state, sessionId)
      return { data: null as T }
    }

    const agentSessionStateMatch = matchPath(
      /^\/agent\/sessions\/([^/]+)\/state$/,
      path,
    )
    if (agentSessionStateMatch && method === "GET") {
      const [sessionId] = agentSessionStateMatch
      const session = findAgentCoreSession(state, sessionId)
      if (!session) throw new ApiError("Agent session not found", { status: 404 })
      const turns = state.agentTurnsBySession.get(sessionId) ?? []
      const events = turns.flatMap((turn) => state.agentEventsByTurn.get(turn.id) ?? [])
      return {
        data: {
          session: clone(session),
          turns: clone(turns),
          events: clone(events).sort((a, b) => a.seq - b.seq),
        } as T,
      }
    }

    const agentSessionTurnsMatch = matchPath(
      /^\/agent\/sessions\/([^/]+)\/turns$/,
      path,
    )
    if (agentSessionTurnsMatch && method === "GET") {
      const [sessionId] = agentSessionTurnsMatch
      return {
        data: clone(state.agentTurnsBySession.get(sessionId) ?? []) as T,
      }
    }

    if (agentSessionTurnsMatch && method === "POST") {
      const [sessionId] = agentSessionTurnsMatch
      const inputText =
        typeof bodyJson?.input_text === "string" ? bodyJson.input_text : ""
      const activeSkillNames = Array.isArray(bodyJson?.active_skill_names)
        ? bodyJson.active_skill_names.filter((name): name is string => typeof name === "string")
        : []
      const turn = createAgentCoreTurn(state, sessionId, inputText, activeSkillNames)
      return { data: clone(turn) as T }
    }

    const agentTurnEventsMatch = matchPath(
      /^\/agent\/turns\/([^/]+)\/events$/,
      path,
    )
    if (agentTurnEventsMatch && method === "GET") {
      const [turnId] = agentTurnEventsMatch
      const afterSeq =
        typeof params.after_seq === "number"
          ? params.after_seq
          : typeof params.after_seq === "string"
            ? Number(params.after_seq)
            : 0
      const events = (state.agentEventsByTurn.get(turnId) ?? []).filter(
        (event) => event.seq > afterSeq,
      )
      return { data: clone(events) as T }
    }

    const agentTurnInterruptMatch = matchPath(
      /^\/agent\/turns\/([^/]+)\/interrupt$/,
      path,
    )
    if (agentTurnInterruptMatch && method === "POST") {
      const [turnId] = agentTurnInterruptMatch
      const turn = findAgentCoreTurn(state, turnId)
      if (!turn) throw new ApiError("Agent turn not found", { status: 404 })
      const interrupted: AgentCoreTurn = {
        ...turn,
        status: "cancelled",
        error_code: null,
        error_message: null,
        updated_at: nowStamp(),
        completed_at: nowStamp(),
      }
      replaceAgentCoreTurn(state, interrupted)
      appendAgentCoreEvent(state, interrupted, "turn.interrupted", {
        termination_reason: "interrupted",
      })
      return { data: clone(interrupted) as T }
    }

    const agentTurnArtifactsMatch = matchPath(
      /^\/agent\/turns\/([^/]+)\/artifacts$/,
      path,
    )
    if (agentTurnArtifactsMatch && method === "GET") {
      const [turnId] = agentTurnArtifactsMatch
      return {
        data: clone(state.agentArtifactsByTurn.get(turnId) ?? []) as T,
      }
    }

    const agentActionDecisionMatch = matchPath(
      /^\/agent\/actions\/([^/]+)\/decision$/,
      path,
    )
    if (agentActionDecisionMatch && method === "POST") {
      const [actionId] = agentActionDecisionMatch
      const action = state.agentActions.get(actionId)
      if (!action) throw new ApiError("Agent action not found", { status: 404 })
      const decision =
        bodyJson?.decision === "reject" || bodyJson?.decision === "modify"
          ? bodyJson.decision
          : "approve"
      const updated: AgentCoreAction = {
        ...action,
        permission_decision: {
          decision,
          note: typeof bodyJson?.note === "string" ? bodyJson.note : null,
          modified_input:
            bodyJson?.modified_input && typeof bodyJson.modified_input === "object"
              ? bodyJson.modified_input
              : null,
        },
        status: decision === "reject" ? "rejected" : "completed",
        audit_summary: `Demo action decision recorded: ${decision}.`,
        updated_at: nowStamp(),
        completed_at: nowStamp(),
      }
      state.agentActions.set(actionId, updated)
      return { data: clone(updated) as T }
    }

    if (path === "/agent/memories" && method === "GET") {
      const projectId =
        typeof params.project_id === "string" ? params.project_id : null
      const status = typeof params.status === "string" ? params.status : null
      const scope = typeof params.scope === "string" ? params.scope : null
      const type = typeof params.type === "string" ? params.type : null
      const memories = state.agentMemories.filter(
        (memory) =>
          (!projectId || memory.project_id === projectId) &&
          (!status || memory.status === status) &&
          (!scope || memory.scope === scope) &&
          (!type || memory.type === type),
      )
      return { data: clone(memories) as T }
    }

    const agentMemoryDecisionMatch = matchPath(
      /^\/agent\/memories\/([^/]+)\/(accept|reject|disable)$/,
      path,
    )
    if (agentMemoryDecisionMatch && method === "POST") {
      const [memoryId, decision] = agentMemoryDecisionMatch
      const index = state.agentMemories.findIndex((memory) => memory.id === memoryId)
      if (index === -1) throw new ApiError("Agent memory not found", { status: 404 })
      const nextStatus =
        decision === "accept"
          ? "accepted"
          : decision === "disable"
            ? "disabled"
            : "rejected"
      const updated: AgentCoreMemory = {
        ...state.agentMemories[index],
        status: nextStatus,
        source: {
          ...(state.agentMemories[index]?.source ?? {}),
          decision_note: typeof bodyJson?.note === "string" ? bodyJson.note : null,
        },
        updated_at: nowStamp(),
      }
      state.agentMemories = state.agentMemories.map((memory) =>
        memory.id === memoryId ? updated : memory,
      )
      return { data: clone(updated) as T }
    }

    if (
      path === "/agent/message" ||
      path === "/agent/conversations" ||
      path.startsWith("/agent/conversations/")
    ) {
      throw new ApiError("Legacy agent API has been replaced by AgentCore", {
        status: 404,
      })
    }

    if (path === "/images" && method === "GET") {
      return {
        data: clone(state.images) as T,
        meta: {
          status: clone(state.imageStatus),
        },
      }
    }

    if (path === "/images/pull" && method === "POST") {
      const name =
        typeof bodyJson?.name === "string" && bodyJson.name.trim()
          ? bodyJson.name.trim()
          : null
      const tag =
        typeof bodyJson?.tag === "string" && bodyJson.tag.trim()
          ? bodyJson.tag.trim()
          : "latest"
      if (!name) {
        throw new ApiError("Image name is required", { status: 400 })
      }

      const fullName = `${name}:${tag}`
      const existing = state.images.find((image) => image.full_name === fullName)
      const image =
        existing
          ? {
              ...existing,
              status: "local" as const,
              pull_progress: null,
              error_message: null,
              updated_at: nowStamp(),
            }
          : createDemoImage(
              state,
              name,
              tag,
              "local",
              "Imported through the demo runtime.",
            )
      upsertImage(state, image)
      return { data: clone(image) as T }
    }

    if (path === "/images/load" && method === "POST") {
      const uploaded = await readUploadedFile(bodyFormData, "demo-image.tar")
      const normalizedName = uploaded.name
        .replace(/\.(tar|tar\.gz|tgz)$/i, "")
        .replace(/[^a-z0-9._/-]+/gi, "-")
        .replace(/^-+|-+$/g, "")
        .toLowerCase() || `demo-image-${state.imageSequence}`
      const image = createDemoImage(
        state,
        `ghcr.io/demo/${normalizedName}`,
        "1.0.0",
        "local",
        "Loaded from a demo tarball import.",
      )
      upsertImage(state, image)
      return { data: clone(state.images) as T }
    }

    const imageMatch = matchPath(/^\/images\/([^/]+)$/, path)
    if (imageMatch && method === "DELETE") {
      const [imageId] = imageMatch
      const image = state.images.find((candidate) => candidate.id === imageId)
      if (!image) throw new ApiError("Image not found", { status: 404 })
      if (image.status === "pulling") {
        throw new ApiError("Image is still pulling", {
          code: "IMAGE_PULLING",
          status: 409,
        })
      }
      state.images = state.images.filter((candidate) => candidate.id !== imageId)
      syncImageStats(state)
      return { data: null as T }
    }

    const approvalMatch = matchPath(/^\/agent\/approvals\/([^/]+)\/resolve$/, path)
    if (approvalMatch && method === "POST") {
      return {
        data: {
          success: true,
        } as T,
      }
    }

    if (path === "/llm/providers" && method === "GET") {
      return { data: clone(state.llmProviders) as T }
    }

    if (path === "/llm/configuration" && method === "GET") {
      return { data: llmConfiguration(state) as T }
    }

    if (path === "/llm/provider-templates" && method === "GET") {
      return { data: clone(DEMO_LLM_PROVIDER_TEMPLATES) as T }
    }

    if (path === "/llm/provider-setups" && method === "POST") {
      return { data: setupDemoProvider(state, bodyJson) as T }
    }

    if (path === "/llm/providers" && method === "POST") {
      const providerId = `llm-provider-demo-${String(state.llmProviderSequence).padStart(3, "0")}`
      state.llmProviderSequence += 1
      const provider: LlmProvider = {
        id: providerId,
        name:
          typeof bodyJson?.name === "string" && bodyJson.name.trim()
            ? bodyJson.name.trim()
            : `Demo provider ${state.llmProviderSequence - 1}`,
        kind:
          typeof bodyJson?.kind === "string"
            ? (bodyJson.kind as LlmProviderKind)
            : "openai_compatible",
        wire_protocol: readDemoWireProtocol(bodyJson?.wire_protocol),
        base_url:
          typeof bodyJson?.base_url === "string" && bodyJson.base_url.trim()
            ? bodyJson.base_url.trim()
            : null,
        api_key_ref:
          typeof bodyJson?.api_key_ref === "string" && bodyJson.api_key_ref.trim()
            ? bodyJson.api_key_ref.trim()
            : null,
        scope:
          typeof bodyJson?.scope === "string"
            ? (bodyJson.scope as LlmProviderScope)
            : "workspace",
        workspace_id: "workspace-demo",
        user_id: null,
        enabled: bodyJson?.enabled !== false,
        allow_insecure_http: bodyJson?.allow_insecure_http === true,
        test_status: null,
        metadata:
          bodyJson?.metadata && typeof bodyJson.metadata === "object"
            ? (bodyJson.metadata as Record<string, unknown>)
            : { demo: true },
        created_at: nowStamp(),
        updated_at: nowStamp(),
      }
      state.llmProviders = [provider, ...state.llmProviders]
      return { data: clone(provider) as T }
    }

    const llmProviderCredentialMatch = matchPath(
      /^\/llm\/providers\/([^/]+)\/credential$/,
      path,
    )
    if (llmProviderCredentialMatch && method === "PUT") {
      const [providerId] = llmProviderCredentialMatch
      const existing = state.llmProviders.find((provider) => provider.id === providerId)
      if (!existing) throw new ApiError("LLM provider not found", { status: 404 })
      const source =
        typeof bodyJson?.source === "string"
          ? (bodyJson.source as LlmProviderCredential["source"])
          : "none"
      if (source === "env") {
        state.llmProviderCredentials[providerId] = {
          provider_id: providerId,
          source: "env",
          configured: true,
          available: true,
          env_var_name:
            typeof bodyJson?.env_var_name === "string"
              ? bodyJson.env_var_name
              : "DEMO_MODEL_KEY",
          fingerprint: null,
          masked_hint:
            typeof bodyJson?.env_var_name === "string"
              ? `env:${bodyJson.env_var_name}`
              : "env:DEMO_MODEL_KEY",
          updated_at: nowStamp(),
        }
      } else {
        setDemoCredential(
          state,
          providerId,
          typeof bodyJson?.secret === "string" ? bodyJson.secret : null,
          source,
        )
      }
      return { data: clone(state.llmProviderCredentials[providerId]) as T }
    }

    const llmProviderMatch = matchPath(/^\/llm\/providers\/([^/]+)$/, path)
    if (llmProviderMatch && method === "PATCH") {
      const [providerId] = llmProviderMatch
      const existing = state.llmProviders.find((provider) => provider.id === providerId)
      if (!existing) throw new ApiError("LLM provider not found", { status: 404 })
      const updated: LlmProvider = {
        ...existing,
        name:
          typeof bodyJson?.name === "string" && bodyJson.name.trim()
            ? bodyJson.name.trim()
            : existing.name,
        kind:
          typeof bodyJson?.kind === "string"
            ? (bodyJson.kind as LlmProviderKind)
            : existing.kind,
        wire_protocol: readDemoWireProtocol(
          bodyJson?.wire_protocol,
          existing.wire_protocol,
        ),
        base_url:
          bodyJson && Object.hasOwn(bodyJson, "base_url")
            ? (bodyJson.base_url as string | null)
            : existing.base_url,
        api_key_ref:
          bodyJson && Object.hasOwn(bodyJson, "api_key_ref")
            ? (bodyJson.api_key_ref as string | null)
            : existing.api_key_ref,
        enabled:
          typeof bodyJson?.enabled === "boolean"
            ? bodyJson.enabled
            : existing.enabled,
        allow_insecure_http:
          typeof bodyJson?.allow_insecure_http === "boolean"
            ? bodyJson.allow_insecure_http
            : existing.allow_insecure_http,
        updated_at: nowStamp(),
      }
      state.llmProviders = state.llmProviders.map((provider) =>
        provider.id === providerId ? updated : provider,
      )
      return { data: clone(updated) as T }
    }

    const llmProviderTestMatch = matchPath(
      /^\/llm\/providers\/([^/]+)\/test$/,
      path,
    )
    if (llmProviderTestMatch && method === "POST") {
      const [providerId] = llmProviderTestMatch
      const existing = state.llmProviders.find((provider) => provider.id === providerId)
      if (!existing) throw new ApiError("LLM provider not found", { status: 404 })
      const requestedModelId =
        typeof bodyJson?.model_id === "string" ? bodyJson.model_id : null
      const testedModel =
        (requestedModelId
          ? state.llmModels.find(
              (model) =>
                model.id === requestedModelId && model.provider_id === providerId,
            )
          : undefined) ??
        state.llmModels.find((model) => model.provider_id === providerId)
      const result: LlmProviderTestResult = {
        provider_id: providerId,
        success: true,
        model: testedModel?.model_id ?? null,
        wire_protocol: existing.wire_protocol,
        error_code: null,
        error: null,
        latency_ms: 29,
        retryable: false,
        http_status: null,
        provider_code: null,
      }
      state.llmProviders = state.llmProviders.map((provider) =>
        provider.id === providerId
          ? {
              ...provider,
              test_status: {
                success: result.success,
                model: result.model,
                wire_protocol: result.wire_protocol,
                error_code: result.error_code,
                error: result.error,
                latency_ms: result.latency_ms,
                retryable: result.retryable,
                http_status: result.http_status,
                provider_code: result.provider_code,
              },
              updated_at: nowStamp(),
            }
          : provider,
      )
      return { data: clone(result) as T }
    }

    if (path === "/llm/models" && method === "GET") {
      const providerId =
        typeof params.provider_id === "string" ? params.provider_id : null
      const models = providerId
        ? state.llmModels.filter((model) => model.provider_id === providerId)
        : state.llmModels
      return { data: clone(models) as T }
    }

    if (path === "/llm/model-profiles" && method === "GET") {
      return { data: clone(state.llmModelProfiles) as T }
    }

    if (path === "/files" && method === "GET") {
      const projectId = params.project_id as string
      const pathParam = (params.path as string | undefined) ?? "."
      const nodes = state.workspaceFiles.get(projectId) ?? []
      return {
        data: {
          path: pathParam,
          files: listChildren(nodes, pathParam),
        } as T,
      }
    }

    if (path === "/files" && method === "DELETE") {
      return { data: null as T }
    }

    if (path === "/files/upload" && method === "POST") {
      const projectId =
        (bodyFormData?.get("project_id") as string | null) ??
        state.scenario.contextDefaults.selectedProjectId
      const uploaded = await readUploadedFile(bodyFormData, "demo-upload.txt")
      upsertWorkspaceFile(
        state,
        projectId,
        `deliveries/${uploaded.name}`,
        uploaded.content,
        uploaded.size,
      )
      return {
        data: {
          ok: true,
        } as T,
      }
    }

    if (path === "/runs/uploads" && method === "POST") {
      const projectId =
        (bodyFormData?.get("project_id") as string | null) ??
        state.scenario.contextDefaults.selectedProjectId
      const uploaded = await readUploadedFile(bodyFormData, "demo-upload.txt")
      const uri = `deliveries/${uploaded.name}`
      upsertWorkspaceFile(state, projectId, uri, uploaded.content, uploaded.size)
      return {
        data: {
          uri,
        } as T,
      }
    }

    if (path === "/files/read" && method === "GET") {
      const projectId = params.project_id as string
      const pathParam = params.path as string
      const nodes = state.workspaceFiles.get(projectId) ?? []
      const node = findFileNode(nodes, pathParam)
      if (!node || node.type !== "file") {
        throw new ApiError("File not found", { status: 404 })
      }
      return {
        data: {
          content: node.content,
        } as T,
      }
    }

    if (path === "/notifications" && method === "POST") {
      return {
        data: {
          id: `notification-${Date.now()}`,
          ...(bodyJson ?? {}),
          enabled: true,
        } as T,
      }
    }

    const notificationMatch = matchPath(/^\/notifications\/([^/]+)$/, path)
    if (notificationMatch && method === "DELETE") {
      return { data: null as T }
    }

    throw new ApiError(`Demo runtime does not handle ${method} ${path}`, {
      status: 404,
    })
  }

  return {
    mode: "demo",
    capabilities: {
      auth: false,
      terminal: false,
      destructiveActions: false,
    },
    contextDefaults: DEMO_RUNTIME_SCENARIO.contextDefaults,
    request,
    buildApiUrl(path: string, params?: RequestParams) {
      if (path.includes("/outputs/download")) {
        return encodeDataUrl("Demo Results Download", `Requested: ${path}`)
      }
      if (path === "/files/download") {
        const filePath = String(params?.path ?? "demo.txt")
        return encodeDataUrl("Demo File Download", `Requested: ${filePath}`)
      }
      return encodeDataUrl("Demo Link", `Requested: ${path}`)
    },
    buildWebSocketUrl() {
      return "ws://demo.invalid/runtime-disabled"
    },
    subscribe(options: RuntimeEventSubscription) {
      const id = ++state.subscriptionSequence
      state.subscribers.set(id, options)
      options.onOpen?.()
      return () => {
        state.subscribers.delete(id)
      }
    },
  }
}

let runtimeSingleton: AppRuntime | null = null

export function createDemoRuntime() {
  return createDemoRuntimeInternal()
}

export function getDemoRuntimeSingleton() {
  if (!runtimeSingleton || runtimeSingleton.mode !== "demo") {
    runtimeSingleton = createDemoRuntimeInternal()
  }
  return runtimeSingleton
}
