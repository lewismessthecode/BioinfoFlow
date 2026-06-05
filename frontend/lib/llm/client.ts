import { apiRequest } from "@/lib/api"
import type {
  LlmModel,
  LlmModelProfile,
  LlmProvider,
  LlmProviderKind,
  LlmProviderScope,
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

export type UpdateLlmProviderInput = Partial<CreateLlmProviderInput>

export const listLlmProviders = async () => {
  const response = await apiRequest<LlmProvider[]>("/llm/providers")
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

export const listLlmModels = async (providerId?: string) => {
  const response = await apiRequest<LlmModel[]>("/llm/models", {
    params: providerId ? { provider_id: providerId } : undefined,
  })
  return response.data
}

export const listLlmModelProfiles = async () => {
  const response = await apiRequest<LlmModelProfile[]>("/llm/model-profiles")
  return response.data
}
