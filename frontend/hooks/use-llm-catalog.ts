"use client"

import { useCallback, useEffect, useState } from "react"

import {
  createLlmProvider,
  discoverLlmProviderModels,
  getLlmConfiguration,
  getLlmProviderTemplates,
  setupLlmProvider,
  testLlmProvider,
  updateLlmProviderCredential,
  updateLlmProvider,
  type CreateLlmProviderInput,
  type UpdateLlmProviderCredentialInput,
} from "@/lib/llm"
import type {
  LlmConfiguredProvider,
  LlmConfiguration,
  LlmModel,
  LlmModelProfile,
  LlmProvider,
  LlmProviderSetupInput,
  LlmProviderSetupResult,
  LlmProviderTemplate,
  LlmProviderTestResult,
} from "@/lib/llm"

export function useLlmCatalog() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [configuredProviders, setConfiguredProviders] = useState<LlmConfiguredProvider[]>([])
  const [models, setModels] = useState<LlmModel[]>([])
  const [profiles, setProfiles] = useState<LlmModelProfile[]>([])
  const [providerTemplates, setProviderTemplates] = useState<LlmProviderTemplate[]>([])
  const [configuration, setConfiguration] = useState<LlmConfiguration | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [nextConfiguration, nextProviderTemplates] = await Promise.all([
        getLlmConfiguration(),
        getLlmProviderTemplates(),
      ])
      setConfiguration(nextConfiguration)
      setConfiguredProviders(nextConfiguration.providers)
      setProviders(nextConfiguration.providers)
      setModels(nextConfiguration.models)
      setProfiles(nextConfiguration.profiles)
      setProviderTemplates(nextProviderTemplates)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Failed to load LLM catalog"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const createProvider = useCallback(
    async (input: CreateLlmProviderInput) => {
      setIsMutating(true)
      setError(null)
      try {
        const provider = await createLlmProvider(input)
        await refresh()
        return provider
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to create LLM provider"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  const setupProvider = useCallback(
    async (input: LlmProviderSetupInput): Promise<LlmProviderSetupResult | null> => {
      setIsMutating(true)
      setError(null)
      try {
        const result = await setupLlmProvider(input)
        await refresh()
        return result
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to set up LLM provider"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  const setProviderEnabled = useCallback(
    async (provider: LlmProvider, enabled: boolean) => {
      setIsMutating(true)
      setError(null)
      try {
        const updated = await updateLlmProvider(provider.id, { enabled })
        await refresh()
        return updated
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to update LLM provider"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  const updateProvider = useCallback(
    async (providerId: string, updates: Parameters<typeof updateLlmProvider>[1]) => {
      setIsMutating(true)
      setError(null)
      try {
        const updated = await updateLlmProvider(providerId, updates)
        await refresh()
        return updated
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to update LLM provider"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  const testProvider = useCallback(
    async (providerId: string): Promise<LlmProviderTestResult | null> => {
      setIsMutating(true)
      setError(null)
      try {
        const result = await testLlmProvider(providerId)
        await refresh()
        return result
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to test LLM provider"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  const discoverModels = useCallback(
    async (providerId: string): Promise<LlmModel[] | null> => {
      setIsMutating(true)
      setError(null)
      try {
        const discovered = await discoverLlmProviderModels(providerId)
        await refresh()
        return discovered
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to discover LLM models"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  const updateCredential = useCallback(
    async (providerId: string, input: UpdateLlmProviderCredentialInput) => {
      setIsMutating(true)
      setError(null)
      try {
        const credential = await updateLlmProviderCredential(providerId, input)
        await refresh()
        return credential
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to update LLM provider credential"))
        return null
      } finally {
        setIsMutating(false)
      }
    },
    [refresh],
  )

  return {
    providers,
    configuredProviders,
    models,
    profiles,
    providerTemplates,
    configuration,
    isLoading,
    isMutating,
    error,
    refresh,
    setupProvider,
    createProvider,
    updateProvider,
    setProviderEnabled,
    testProvider,
    discoverModels,
    updateCredential,
  }
}
