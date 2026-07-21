export type LlmProviderKind = string

export type LlmProviderScope = "global" | "workspace" | "user"
export type LlmWireProtocol = "chat_completions" | "responses"

export type LlmProvider = {
  id: string
  name: string
  kind: LlmProviderKind
  wire_protocol: LlmWireProtocol
  base_url?: string | null
  api_key_ref?: string | null
  scope: LlmProviderScope
  workspace_id?: string | null
  user_id?: string | null
  enabled: boolean
  allow_insecure_http: boolean
  test_status?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type LlmProviderCredentialSource = "none" | "env" | "stored"

export type LlmProviderCredential = {
  provider_id: string
  source: LlmProviderCredentialSource
  configured: boolean
  available: boolean
  env_var_name?: string | null
  fingerprint?: string | null
  masked_hint?: string | null
  updated_at?: string | null
}

export type LlmConfiguredProvider = LlmProvider & {
  credential: LlmProviderCredential
}

export type LlmModel = {
  id: string
  provider_id: string
  model_id: string
  display_name: string
  context_length?: number | null
  max_output_tokens?: number | null
  supports_tools: boolean
  supports_streaming: boolean
  supports_vision: boolean
  supports_json_schema: boolean
  supports_reasoning: boolean
  default_temperature?: string | null
  default_top_p?: string | null
  cost_metadata?: Record<string, unknown> | null
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type LlmModelProfile = {
  id: string
  name: string
  task_type: string
  primary_model_id: string
  fallback_model_ids?: string[] | null
  reasoning_budget?: number | null
  max_tokens?: number | null
  cost_ceiling?: string | null
  routing_policy?: Record<string, unknown> | null
  permission_overrides?: Record<string, unknown> | null
  scope: LlmProviderScope
  workspace_id?: string | null
  user_id?: string | null
  enabled: boolean
  metadata?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export type LlmProviderTestResult = {
  provider_id: string
  success: boolean
  model?: string | null
  wire_protocol: LlmWireProtocol
  error_code?: string | null
  error?: string | null
  latency_ms?: number | null
  retryable: boolean
  http_status?: number | null
  provider_code?: string | null
  failed_at?: "configuration" | "catalog" | "runtime" | null
  checks?: Array<{
    name: "configuration" | "catalog" | "runtime"
    status: "passed" | "failed" | "skipped"
    error_code?: string | null
    message?: string | null
  }>
}

export type LlmProviderDiscovery =
  | "static"
  | "openai_models"
  | "ollama_tags"
  | "anthropic_models"
  | "openrouter_models"
  | "gemini_models"
  | "cohere_models"

export type LlmProviderTemplateField = {
  name: "api_key" | "base_url" | "model_id" | string
  label: string
  secret: boolean
  required: boolean
  placeholder: string
  default?: string | null
}

export type LlmProviderTemplateModel = {
  id: string
  name: string
  context_length?: number | null
  max_output_tokens?: number | null
  supports_tools: boolean
  supports_streaming: boolean
  supports_vision: boolean
  supports_json_schema: boolean
  supports_reasoning: boolean
}

export type LlmProviderTemplate = {
  id: string
  name: string
  kind: LlmProviderKind
  docs_url: string
  discovery: LlmProviderDiscovery
  default_base_url?: string | null
  supported_wire_protocols?: LlmWireProtocol[]
  default_wire_protocol?: LlmWireProtocol
  fields: LlmProviderTemplateField[]
  models: LlmProviderTemplateModel[]
}

export type LlmConfiguration = {
  summary: {
    provider_count: number
    configured_provider_count: number
    available_provider_count: number
    model_count: number
    profile_count: number
  }
  providers: LlmConfiguredProvider[]
  models: LlmModel[]
  profiles: LlmModelProfile[]
}

export type LlmProviderSetupInput = {
  templateId: string
  providerId?: string | null
  name?: string | null
  baseUrl?: string | null
  apiKey?: string | null
  wireProtocol?: LlmWireProtocol
  modelIds?: string[] | null
  discover?: boolean
  scope?: LlmProviderScope
  enabled?: boolean
  allowInsecureHttp?: boolean
}

export type LlmProviderSetupResult = {
  provider: LlmConfiguredProvider
  models: LlmModel[]
  discovered: boolean
}
