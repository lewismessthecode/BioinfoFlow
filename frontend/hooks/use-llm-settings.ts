"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiError, getApiErrorMessage } from "@/lib/api"
import { getLlmConfiguration, testLlmProvider } from "@/lib/llm"
import type {
  LlmConfiguration,
  LlmConfiguredProvider,
} from "@/lib/llm"

export type ProviderModelInfo = {
  id: string
  name: string
  model_id?: string
  context_window: number | null
  supports_vision: boolean
}

export type ProviderModels = {
  provider: string
  provider_kind: string
  label: string
  base_url?: string | null
  models: ProviderModelInfo[]
}

export type LlmRuntimeSettings = {
  selected_provider: string
  selected_model: string
  configured_providers: string[]
}

export type ModelSelection = {
  provider?: string | null
  model?: string | null
  model_id?: string | null
}

type ProviderTestResult = {
  provider: string
  success: boolean
  error: string | null
  model: string | null
}

const isUnauthorizedError = (error: unknown) =>
  error instanceof ApiError && error.status === 401

const MODEL_STORAGE_KEY = "bioinfoflow:selected-model"
const PROVIDER_STORAGE_KEY = "bioinfoflow:selected-provider"
const MODEL_ID_STORAGE_KEY = "bioinfoflow:selected-catalog-model-id"

function getStoredSelection(): ModelSelection | null {
  if (typeof window === "undefined") return null
  const provider = window.localStorage.getItem(PROVIDER_STORAGE_KEY) || ""
  const model = window.localStorage.getItem(MODEL_STORAGE_KEY) || ""
  const modelId = window.localStorage.getItem(MODEL_ID_STORAGE_KEY) || ""
  if (!provider || !model) return null
  return { provider, model, model_id: modelId || null }
}

function persistSelection(selection: ModelSelection | null) {
  if (typeof window === "undefined") return
  if (selection) {
    window.localStorage.setItem(PROVIDER_STORAGE_KEY, selection.provider ?? "")
    window.localStorage.setItem(MODEL_STORAGE_KEY, selection.model ?? "")
    if (selection.model_id) {
      window.localStorage.setItem(MODEL_ID_STORAGE_KEY, selection.model_id)
    } else {
      window.localStorage.removeItem(MODEL_ID_STORAGE_KEY)
    }
    return
  }
  window.localStorage.removeItem(PROVIDER_STORAGE_KEY)
  window.localStorage.removeItem(MODEL_STORAGE_KEY)
  window.localStorage.removeItem(MODEL_ID_STORAGE_KEY)
}

function selectionInModels(
  selection: ModelSelection | null,
  models: ProviderModels[],
): ModelSelection | null {
  if (!selection?.provider || !selection.model) return null
  const directProvider = models.find(
    (group) => group.provider === selection.provider,
  )
  const legacyProviders = models.filter(
    (group) =>
      group.provider_kind === selection.provider &&
      group.models.some((item) => item.id === selection.model),
  )
  const provider = directProvider ?? (
    legacyProviders.length === 1 ? legacyProviders[0] : undefined
  )
  const model = provider?.models.find((item) => item.id === selection.model)
  if (!provider || !model) return null
  return {
    provider: provider.provider,
    model: model.id,
    model_id: model.model_id,
  }
}

function resolveSelection(
  settings: LlmRuntimeSettings | null,
  models: ProviderModels[],
): ModelSelection | null {
  if (
    settings?.selected_provider &&
    settings.selected_provider !== "auto" &&
    settings.selected_model
  ) {
    const matchedSelection = selectionInModels(
      {
        provider: settings.selected_provider,
        model: settings.selected_model,
      },
      models,
    )
    if (matchedSelection) return matchedSelection
  }

  if (settings?.selected_model) {
    const matchedProvider = models.find((providerGroup) =>
      providerGroup.models.some((model) => model.id === settings.selected_model),
    )
    if (matchedProvider) {
      const matchedModel = matchedProvider.models.find(
        (model) => model.id === settings.selected_model,
      )
      return {
        provider: matchedProvider.provider,
        model: settings.selected_model,
        model_id: matchedModel?.model_id,
      }
    }
  }

  return selectionInModels(getStoredSelection(), models)
}

function providerAvailable(provider: LlmConfiguredProvider) {
  // Rely on the credential semantics the backend already computes. Keyless local
  // providers (e.g. a hand-configured Ollama) surface as `available` or, when
  // optional, `source === "none"`; we no longer special-case provider.kind, so a
  // stale built-in entry can never masquerade as configured.
  return Boolean(
    provider.enabled &&
      (provider.credential?.available || provider.credential?.source === "none"),
  )
}

const SCOPE_ORDER: Record<string, number> = { user: 0, workspace: 1, global: 2 }
const PREFERRED_ENV_KINDS = new Set(["vllm", "openai_compatible"])

function defaultProviderRank(provider: LlmConfiguredProvider): [number, number] {
  // Mirror the backend default-selection precedence so the UI's default model
  // matches what the agent runtime would pick: closest scope first, then an
  // explicitly env-managed vLLM/OpenAI-compatible endpoint ahead of incidental
  // providers (such as a previously seeded local default).
  const scopeRank = SCOPE_ORDER[provider.scope] ?? 3
  const metadata = (provider.metadata ?? {}) as { envManaged?: unknown }
  const envManaged = metadata.envManaged === true
  const kindRank = envManaged && PREFERRED_ENV_KINDS.has(provider.kind) ? 0 : 1
  return [scopeRank, kindRank]
}

function compareProvidersForDefault(
  a: LlmConfiguredProvider,
  b: LlmConfiguredProvider,
): number {
  const [aScope, aKind] = defaultProviderRank(a)
  const [bScope, bKind] = defaultProviderRank(b)
  return aScope - bScope || aKind - bKind
}

function modelsFromConfiguration(data: LlmConfiguration): ProviderModels[] {
  return data.providers
    .filter(providerAvailable)
    .sort(compareProvidersForDefault)
    .map((provider) => ({
      provider: provider.id,
      provider_kind: provider.kind,
      label: provider.name,
      base_url: provider.base_url ?? null,
      models: data.models
        .filter((model) => model.provider_id === provider.id)
        .map((model) => ({
          id: model.model_id,
          name: model.display_name,
          context_window: model.context_length ?? null,
          model_id: model.id,
          supports_vision: model.supports_vision ?? false,
        })),
    }))
    .filter((group) => group.models.length > 0)
}

export function useLlmSettings() {
  const [settings, setSettings] = useState<LlmRuntimeSettings | null>(null)
  const [models, setModels] = useState<ProviderModels[]>([])
  const [configuredProviders, setConfiguredProviders] = useState<
    LlmConfiguredProvider[]
  >([])
  const [isLoading, setIsLoading] = useState(true)
  const [configurationError, setConfigurationError] = useState<string | null>(null)

  const fetchSettings = useCallback(async () => {
    try {
      setConfigurationError(null)
      const data = await getLlmConfiguration()
      const nextModels = modelsFromConfiguration(data)
      const configuredProviderKeys = data.providers
        .filter(providerAvailable)
        .map((provider) => provider.kind)

      setConfiguredProviders(data.providers)
      setModels(nextModels)

      const stored = selectionInModels(getStoredSelection(), nextModels)
      const firstModel = nextModels[0]?.models[0]
      const inferred = stored ?? (
        firstModel
          ? {
              provider: nextModels[0]?.provider,
              model: firstModel.id,
              model_id: firstModel.model_id,
            }
          : null
      )
      setSettings({
        selected_provider: inferred?.provider ?? "auto",
        selected_model: inferred?.model ?? "",
        configured_providers: Array.from(new Set(configuredProviderKeys)),
      })
    } catch (error) {
      setSettings(null)
      setModels([])
      setConfiguredProviders([])
      setConfigurationError(
        isUnauthorizedError(error)
          ? null
          : getApiErrorMessage(error, "LLM configuration is unavailable"),
      )
    }
  }, [])

  useEffect(() => {
    void (async () => {
      setIsLoading(true)
      await fetchSettings()
      setIsLoading(false)
    })()
  }, [fetchSettings])

  const testProvider = useCallback(
    async (provider: string) => {
      const target = configuredProviders.find(
        (item) =>
          item.id === provider ||
          item.kind === provider ||
          item.name.toLowerCase() === provider.toLowerCase(),
      )
      if (!target) {
        return {
          provider,
          success: false,
          error: "Provider is not configured",
          model: null,
        } as ProviderTestResult
      }

      try {
        const result = await testLlmProvider(target.id)
        return {
          provider,
          success: result.success,
          error: result.error ?? null,
          model: result.model ?? null,
        } as ProviderTestResult
      } catch (error) {
        return {
          provider,
          success: false,
          error: getApiErrorMessage(error, "Connection test failed"),
          model: null,
        } as ProviderTestResult
      }
    },
    [configuredProviders],
  )

  const setSelectedModel = useCallback(
    async (selection: ModelSelection | null) => {
      persistSelection(selection)
      setSettings((current) =>
        current
          ? {
              ...current,
              selected_provider: selection?.provider ?? "auto",
              selected_model: selection?.model ?? "",
            }
          : current,
      )
    },
    [],
  )

  const hasConfiguredProvider =
    settings !== null && settings.configured_providers.length > 0

  const selectedModel = resolveSelection(settings, models)

  useEffect(() => {
    if (isLoading) return
    persistSelection(selectedModel)
  }, [isLoading, selectedModel])

  const allModels = models.flatMap((providerModels) =>
    providerModels.models.map((model) => ({
      ...model,
      provider: providerModels.provider,
    })),
  )

  return {
    settings,
    models,
    allModels,
    isLoading,
    configurationError,
    configurationUnavailable: configurationError !== null,
    hasConfiguredProvider,
    selectedModel,
    setSelectedModel,
    testProvider,
    refresh: fetchSettings,
    refetch: async () => {
      await fetchSettings()
    },
  }
}
