"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { ApiError, apiRequest, getApiErrorMessage } from "@/lib/api"

export type ProviderModelInfo = {
  id: string
  name: string
  model_id?: string
  context_window: number | null
}

export type ProviderModels = {
  provider: string
  label: string
  models: ProviderModelInfo[]
}

export type UserLlmSettings = {
  provider_credentials: Record<string, Record<string, string>>
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
  const provider = models.find((group) => group.provider === selection.provider)
  const model = provider?.models.find((item) => item.id === selection.model)
  if (!provider || !model) return null
  return {
    provider: provider.provider,
    model: model.id,
    model_id: model.model_id,
  }
}

function resolveSelection(
  settings: UserLlmSettings | null,
  models: ProviderModels[],
): ModelSelection | null {
  if (settings?.selected_provider && settings.selected_provider !== "auto" && settings.selected_model) {
    const matchedProvider = models.find((providerGroup) =>
      providerGroup.models.some((model) => model.id === settings.selected_model),
    )
    const matchedModel = matchedProvider?.models.find(
      (model) => model.id === settings.selected_model,
    )
    return {
      provider: settings.selected_provider,
      model: settings.selected_model,
      model_id: matchedModel?.model_id,
    }
  }

  if (settings?.selected_model) {
    const matchedProvider = models.find((providerGroup) =>
      providerGroup.models.some((model) => model.id === settings.selected_model),
    )
    if (matchedProvider) {
      const matchedModel = matchedProvider.models.find((model) => model.id === settings.selected_model)
      return {
        provider: matchedProvider.provider,
        model: settings.selected_model,
        model_id: matchedModel?.model_id,
      }
    }
  }

  return selectionInModels(getStoredSelection(), models)
}

export function useLlmSettings() {
  const [settings, setSettings] = useState<UserLlmSettings | null>(null)
  const [models, setModels] = useState<ProviderModels[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [configurationError, setConfigurationError] = useState<string | null>(null)

  const fetchSettings = useCallback(async () => {
    try {
      setConfigurationError(null)
      const { data } = await apiRequest<{
        providers: Array<{
          id: string
          name: string
          kind: string
          metadata?: Record<string, unknown> | null
          credential?: {
            configured?: boolean
            available?: boolean
            source?: string
          }
        }>
        models: Array<{
          id: string
          provider_id: string
          model_id: string
          display_name: string
          context_length?: number | null
        }>
      }>("/llm/configuration")
      const isProviderAvailable = (provider: (typeof data.providers)[number]) =>
        Boolean(
          provider.credential?.available ||
            provider.kind === "ollama" ||
            provider.metadata?.authMode === "none",
        )
      const configuredProviderKeys = data.providers
        .filter(isProviderAvailable)
        .map((provider) => provider.kind)
      const nextModels = data.providers
        .filter(isProviderAvailable)
        .map((provider) => ({
          provider: provider.kind,
          label: provider.name,
          models: data.models
            .filter((model) => model.provider_id === provider.id)
            .map((model) => ({
              id: model.model_id,
              name: model.display_name,
              context_window: model.context_length ?? null,
              model_id: model.id,
            })),
        }))
        .filter((group) => group.models.length > 0)
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
        provider_credentials: {},
        selected_provider: inferred?.provider ?? "auto",
        selected_model: inferred?.model ?? "",
        configured_providers: Array.from(new Set(configuredProviderKeys)),
      })
    } catch (error) {
      setSettings(null)
      setModels([])
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

  const updateSettings = useCallback(
    async (updates: Partial<UserLlmSettings>) => {
      try {
        const { data } = await apiRequest<UserLlmSettings>("/user-settings", {
          method: "PATCH",
          body: JSON.stringify(updates),
        })
        setSettings(data)
        await fetchSettings()
        return data
      } catch (error) {
        const message = getApiErrorMessage(error, "Failed to update settings")
        toast.error(message)
        throw error
      }
    },
    [fetchSettings]
  )

  const testProvider = useCallback(async (provider: string) => {
    try {
      const { data } = await apiRequest<ProviderTestResult>(
        `/user-settings/test/${provider}`,
        { method: "POST" }
      )
      return data
    } catch (error) {
      return {
        provider,
        success: false,
        error: getApiErrorMessage(error, "Connection test failed"),
        model: null,
      } as ProviderTestResult
    }
  }, [])

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
    []
  )

  const hasConfiguredProvider =
    settings !== null && settings.configured_providers.length > 0

  const selectedModel = resolveSelection(settings, models)

  useEffect(() => {
    persistSelection(selectedModel)
  }, [selectedModel])

  // Flat list of all available models with provider info
  const allModels = models.flatMap((pm) =>
    pm.models.map((m) => ({ ...m, provider: pm.provider }))
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
    updateSettings,
    setSelectedModel,
    testProvider,
    refetch: async () => {
      await fetchSettings()
    },
  }
}
