"use client"

import { useCallback, useEffect, useRef, useState } from "react"

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

export type SetupProviderOutcome =
  | { ok: true; result: LlmProviderSetupResult }
  | { ok: false; error: Error }

export function useLlmCatalog() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [configuredProviders, setConfiguredProviders] = useState<LlmConfiguredProvider[]>([])
  const [models, setModels] = useState<LlmModel[]>([])
  const [profiles, setProfiles] = useState<LlmModelProfile[]>([])
  const [providerTemplates, setProviderTemplates] = useState<LlmProviderTemplate[]>([])
  const [configuration, setConfiguration] = useState<LlmConfiguration | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [pendingMutationCount, setPendingMutationCount] = useState(0)
  const isMutating = pendingMutationCount > 0
  const [error, setError] = useState<Error | null>(null)
  const refreshGeneration = useRef(0)

  const refresh = useCallback(async (options?: { background?: boolean }) => {
    const generation = refreshGeneration.current + 1
    refreshGeneration.current = generation
    const background = options?.background ?? false
    if (!background) setIsLoading(true)
    setError(null)
    try {
      const [nextConfiguration, nextProviderTemplates] = await Promise.all([
        getLlmConfiguration(),
        getLlmProviderTemplates(),
      ])
      if (generation !== refreshGeneration.current) return
      setConfiguration(nextConfiguration)
      setConfiguredProviders(nextConfiguration.providers)
      setProviders(nextConfiguration.providers)
      setModels(nextConfiguration.models)
      setProfiles(nextConfiguration.profiles)
      setProviderTemplates(nextProviderTemplates)
    } catch (caught) {
      if (generation !== refreshGeneration.current) return
      setError(caught instanceof Error ? caught : new Error("Failed to load LLM catalog"))
    } finally {
      if (generation === refreshGeneration.current) setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const createProvider = useCallback(
    async (input: CreateLlmProviderInput) => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const provider = await createLlmProvider(input)
        await refresh({ background: true })
        return provider
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to create LLM provider"))
        return null
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
      }
    },
    [refresh],
  )

  const setupProvider = useCallback(
    async (input: LlmProviderSetupInput): Promise<SetupProviderOutcome> => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const result = await setupLlmProvider(input)
        await refresh({ background: true })
        return { ok: true, result }
      } catch (caught) {
        const setupError =
          caught instanceof Error
            ? caught
            : new Error("Failed to set up LLM provider")
        setError(setupError)
        return { ok: false, error: setupError }
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
      }
    },
    [refresh],
  )

  const setProviderEnabled = useCallback(
    async (provider: LlmProvider, enabled: boolean) => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const updated = await updateLlmProvider(provider.id, { enabled })
        await refresh()
        return updated
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to update LLM provider"))
        return null
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
      }
    },
    [refresh],
  )

  const updateProvider = useCallback(
    async (providerId: string, updates: Parameters<typeof updateLlmProvider>[1]) => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const updated = await updateLlmProvider(providerId, updates)
        await refresh()
        return updated
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to update LLM provider"))
        return null
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
      }
    },
    [refresh],
  )

  const testProvider = useCallback(
    async (
      providerId: string,
      modelId?: string,
    ): Promise<LlmProviderTestResult | null> => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const result = await testLlmProvider(providerId, modelId)
        await refresh({ background: true })
        return result
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to test LLM provider"))
        return null
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
      }
    },
    [refresh],
  )

  const discoverModels = useCallback(
    async (providerId: string): Promise<LlmModel[] | null> => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const discovered = await discoverLlmProviderModels(providerId)
        await refresh()
        return discovered
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to discover LLM models"))
        return null
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
      }
    },
    [refresh],
  )

  const updateCredential = useCallback(
    async (providerId: string, input: UpdateLlmProviderCredentialInput) => {
      setPendingMutationCount((count) => count + 1)
      setError(null)
      try {
        const credential = await updateLlmProviderCredential(providerId, input)
        await refresh()
        return credential
      } catch (caught) {
        setError(caught instanceof Error ? caught : new Error("Failed to update LLM provider credential"))
        return null
      } finally {
        setPendingMutationCount((count) => Math.max(0, count - 1))
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
