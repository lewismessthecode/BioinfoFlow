export type LlmProviderKind =
  | "openai"
  | "anthropic"
  | "gemini"
  | "openrouter"
  | "deepseek"
  | "ollama"
  | "vllm"
  | "openai_compatible"

export type LlmProviderScope = "global" | "workspace" | "user"

export type LlmProvider = {
  id: string
  name: string
  kind: LlmProviderKind
  base_url?: string | null
  api_key_ref?: string | null
  scope: LlmProviderScope
  workspace_id?: string | null
  user_id?: string | null
  enabled: boolean
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
  error?: string | null
  latency_ms?: number | null
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
