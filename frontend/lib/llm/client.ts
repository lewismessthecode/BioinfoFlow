import { apiRequest } from "@/lib/api"
import type {
  LlmConfiguration,
  LlmModel,
  LlmProviderCredential,
  LlmProviderCredentialSource,
  LlmProvider,
  LlmProviderKind,
  LlmProviderScope,
  LlmProviderSetupInput,
  LlmProviderSetupResult,
  LlmProviderTemplate,
  LlmProviderTestResult,
} from "@/lib/llm/types"

export type CreateLlmProviderInput = {
  name: string
  kind: LlmProviderKind
  baseUrl?: string | null
  apiKeyRef?: string | null
  scope?: LlmProviderScope
  enabled?: boolean
  metadata?: Record<string, unknown> | null
}

type UpdateLlmProviderInput = Partial<CreateLlmProviderInput>

export type UpdateLlmProviderCredentialInput = {
  source: LlmProviderCredentialSource
  envVarName?: string | null
  secret?: string | null
}

export const getLlmConfiguration = async () => {
  const response = await apiRequest<LlmConfiguration>("/llm/configuration")
  return response.data
}

export const getLlmProviderTemplates = async () => {
  const response = await apiRequest<LlmProviderTemplate[]>(
    "/llm/provider-templates",
  )
  return response.data
}

export const setupLlmProvider = async (input: LlmProviderSetupInput) => {
  const response = await apiRequest<LlmProviderSetupResult>(
    "/llm/provider-setups",
    {
      method: "POST",
      body: JSON.stringify({
        template_id: input.templateId,
        provider_id: input.providerId || null,
        name: input.name || null,
        base_url: input.baseUrl || null,
        api_key: input.apiKey || null,
        model_ids: input.modelIds ?? [],
        discover: input.discover ?? false,
        scope: input.scope ?? "user",
        enabled: input.enabled ?? true,
      }),
    },
  )
  return response.data
}

export const createLlmProvider = async (input: CreateLlmProviderInput) => {
  const response = await apiRequest<LlmProvider>("/llm/providers", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      kind: input.kind,
      base_url: input.baseUrl || null,
      api_key_ref: input.apiKeyRef || null,
      scope: input.scope ?? "workspace",
      enabled: input.enabled ?? true,
      metadata: input.metadata ?? null,
    }),
  })
  return response.data
}

export const updateLlmProvider = async (
  providerId: string,
  updates: UpdateLlmProviderInput,
) => {
  const response = await apiRequest<LlmProvider>(`/llm/providers/${providerId}`, {
    method: "PATCH",
    body: JSON.stringify({
      name: updates.name,
      kind: updates.kind,
      base_url: updates.baseUrl,
      api_key_ref: updates.apiKeyRef,
      scope: updates.scope,
      enabled: updates.enabled,
      metadata: updates.metadata,
    }),
  })
  return response.data
}

export const testLlmProvider = async (providerId: string) => {
  const response = await apiRequest<LlmProviderTestResult>(
    `/llm/providers/${providerId}/test`,
    { method: "POST" },
  )
  return response.data
}

export const discoverLlmProviderModels = async (providerId: string) => {
  const response = await apiRequest<LlmModel[]>(
    `/llm/providers/${providerId}/discover-models`,
    { method: "POST" },
  )
  return response.data
}

export const updateLlmProviderCredential = async (
  providerId: string,
  input: UpdateLlmProviderCredentialInput,
) => {
  const response = await apiRequest<LlmProviderCredential>(
    `/llm/providers/${providerId}/credential`,
    {
      method: "PUT",
      body: JSON.stringify({
        source: input.source,
        env_var_name: input.envVarName || null,
        secret: input.secret || null,
      }),
    },
  )
  return response.data
}
