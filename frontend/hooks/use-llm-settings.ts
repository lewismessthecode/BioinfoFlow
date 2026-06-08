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

type ProviderTestResult = {
  provider: string
  success: boolean
  error: string | null
  model: string | null
}

const isUnauthorizedError = (error: unknown) =>
  error instanceof ApiError && error.status === 401

export function useLlmSettings() {
  const [settings, setSettings] = useState<UserLlmSettings | null>(null)
  const [models, setModels] = useState<ProviderModels[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const fetchSettings = useCallback(async () => {
    try {
      const { data } = await apiRequest<UserLlmSettings>("/user-settings")
      setSettings(data)
      // Keep the selected model available for AgentCore clients during reloads.
      if (data.selected_model) {
        localStorage.setItem("bioinfoflow:selected-model", data.selected_model)
      }
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
    async (model: string) => {
      localStorage.setItem("bioinfoflow:selected-model", model)
      await updateSettings({ selected_model: model })
    },
    [updateSettings]
  )

  const hasConfiguredProvider =
    settings !== null && settings.configured_providers.length > 0

  const selectedModel =
    settings?.selected_model ||
    (typeof window !== "undefined"
      ? window.localStorage.getItem("bioinfoflow:selected-model") || ""
      : "")

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
