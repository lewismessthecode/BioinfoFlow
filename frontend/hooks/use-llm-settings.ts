"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { ApiError, apiRequest, getApiErrorMessage } from "@/lib/api"
import { logger } from "@/lib/logger"

export type ProviderModelInfo = {
  id: string
  name: string
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
  provider: string
  model: string
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

function getStoredSelection(): ModelSelection | null {
  if (typeof window === "undefined") return null
  const provider = window.localStorage.getItem(PROVIDER_STORAGE_KEY) || ""
  const model = window.localStorage.getItem(MODEL_STORAGE_KEY) || ""
  if (!provider || !model) return null
  return { provider, model }
}

function persistSelection(selection: ModelSelection | null) {
  if (typeof window === "undefined") return
  if (selection) {
    window.localStorage.setItem(PROVIDER_STORAGE_KEY, selection.provider)
    window.localStorage.setItem(MODEL_STORAGE_KEY, selection.model)
    return
  }
  window.localStorage.removeItem(PROVIDER_STORAGE_KEY)
  window.localStorage.removeItem(MODEL_STORAGE_KEY)
}

function resolveSelection(
  settings: UserLlmSettings | null,
  models: ProviderModels[],
): ModelSelection | null {
  if (settings?.selected_provider && settings.selected_provider !== "auto" && settings.selected_model) {
    return {
      provider: settings.selected_provider,
      model: settings.selected_model,
    }
  }

  if (settings?.selected_model) {
    const matchedProvider = models.find((providerGroup) =>
      providerGroup.models.some((model) => model.id === settings.selected_model),
    )
    if (matchedProvider) {
      return {
        provider: matchedProvider.provider,
        model: settings.selected_model,
      }
    }
  }

  return getStoredSelection()
}

export function useLlmSettings() {
  const [settings, setSettings] = useState<UserLlmSettings | null>(null)
  const [models, setModels] = useState<ProviderModels[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await apiRequest<UserLlmSettings>("/user-settings")
      setSettings(data)
    } catch (error) {
      if (isUnauthorizedError(error)) {
        setSettings(null)
        return
      }
      logger.error("Failed to load LLM settings", { error })
    }
  }, [])

  const fetchModels = useCallback(async () => {
    try {
      const { data } = await apiRequest<ProviderModels[]>("/user-settings/models")
      setModels(data)
    } catch (error) {
      if (isUnauthorizedError(error)) {
        setModels([])
        return
      }
      logger.error("Failed to load models", { error })
    }
  }, [])

  useEffect(() => {
    void (async () => {
      setIsLoading(true)
      await Promise.all([fetchSettings(), fetchModels()])
      setIsLoading(false)
    })()
  }, [fetchSettings, fetchModels])

  const updateSettings = useCallback(
    async (updates: Partial<UserLlmSettings>) => {
      try {
        const { data } = await apiRequest<UserLlmSettings>("/user-settings", {
          method: "PATCH",
          body: JSON.stringify(updates),
        })
        setSettings(data)
        // Refresh models since available providers may have changed
        await fetchModels()
        return data
      } catch (error) {
        const message = getApiErrorMessage(error, "Failed to update settings")
        toast.error(message)
        throw error
      }
    },
    [fetchModels]
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
      await updateSettings({
        selected_provider: selection?.provider ?? "auto",
        selected_model: selection?.model ?? "",
      })
    },
    [updateSettings]
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
    hasConfiguredProvider,
    selectedModel,
    updateSettings,
    setSelectedModel,
    testProvider,
    refetch: async () => {
      await Promise.all([fetchSettings(), fetchModels()])
    },
  }
}
