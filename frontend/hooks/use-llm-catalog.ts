"use client"

import { useCallback, useEffect, useState } from "react"

import {
  createLlmProvider,
  listLlmModelProfiles,
  listLlmModels,
  listLlmProviders,
  testLlmProvider,
  updateLlmProvider,
  type CreateLlmProviderInput,
} from "@/lib/llm"
import type {
  LlmModel,
  LlmModelProfile,
  LlmProvider,
  LlmProviderTestResult,
} from "@/lib/llm"

export function useLlmCatalog() {
  const [providers, setProviders] = useState<LlmProvider[]>([])
  const [models, setModels] = useState<LlmModel[]>([])
  const [profiles, setProfiles] = useState<LlmModelProfile[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const refresh = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [nextProviders, nextModels, nextProfiles] = await Promise.all([
        listLlmProviders(),
        listLlmModels(),
        listLlmModelProfiles(),
      ])
      setProviders(nextProviders)
      setModels(nextModels)
      setProfiles(nextProfiles)
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

  return {
    providers,
    models,
    profiles,
    isLoading,
    isMutating,
    error,
    refresh,
    createProvider,
    setProviderEnabled,
    testProvider,
  }
}
