"use client"

import { useCallback, useState } from "react"

import type { SetupProviderOutcome } from "@/hooks/use-llm-catalog"
import type { ModelSelection } from "@/hooks/use-llm-settings"
import type {
  LlmModel,
  LlmProviderSetupInput,
  LlmProviderTestResult,
} from "@/lib/llm"

export type ProviderConnectionFailureStage =
  | "setup"
  | "discovery"
  | "model"
  | "probe"

export type ProviderConnectionOutcome =
  | { ok: true; providerId: string; modelId: string; modelName: string }
  | {
      ok: false
      stage: ProviderConnectionFailureStage
      error: Error
      providerId?: string
    }

export type ProviderConnectionActivationPolicy =
  | {
      mode: "activate"
      setSelectedModel: (selection: ModelSelection | null) => Promise<void>
      refreshSettings: () => Promise<void>
    }
  | { mode: "preserve" }

export type ProviderConnectionOperations = {
  setupProvider: (
    input: LlmProviderSetupInput,
  ) => Promise<SetupProviderOutcome>
  discoverModels: (providerId: string) => Promise<LlmModel[] | null>
  testProvider: (
    providerId: string,
    modelId?: string,
  ) => Promise<LlmProviderTestResult | null>
  activation: ProviderConnectionActivationPolicy
}

function asError(error: unknown, fallback: string) {
  return error instanceof Error ? error : new Error(fallback)
}

export function useProviderConnection(
  operations: ProviderConnectionOperations,
) {
  const [isConnecting, setIsConnecting] = useState(false)

  const connect = useCallback(
    async (
      input: LlmProviderSetupInput,
    ): Promise<ProviderConnectionOutcome> => {
      setIsConnecting(true)
      let providerId: string | undefined

      try {
        let setupOutcome: SetupProviderOutcome
        try {
          setupOutcome = await operations.setupProvider({
            ...input,
            discover: false,
          })
        } catch (error) {
          return {
            ok: false,
            stage: "setup",
            error: asError(error, "Failed to set up provider"),
          }
        }

        if (!setupOutcome.ok) {
          return { ok: false, stage: "setup", error: setupOutcome.error }
        }

        providerId = setupOutcome.result.provider.id
        let availableModels = setupOutcome.result.models

        if (availableModels.length === 0) {
          try {
            const discovered = await operations.discoverModels(providerId)
            if (discovered === null) {
              return {
                ok: false,
                stage: "discovery",
                error: new Error("Model discovery failed"),
                providerId,
              }
            }
            availableModels = discovered
          } catch (error) {
            return {
              ok: false,
              stage: "discovery",
              error: asError(error, "Model discovery failed"),
              providerId,
            }
          }
        }

        const model = availableModels.find(
          (candidate) => candidate.supports_tools === true,
        )
        if (!model) {
          return {
            ok: false,
            stage: "model",
            error: new Error("No tool-capable model was found"),
            providerId,
          }
        }

        let probe: LlmProviderTestResult | null
        try {
          probe = await operations.testProvider(providerId, model.id)
        } catch (error) {
          return {
            ok: false,
            stage: "probe",
            error: asError(error, "Provider connection test failed"),
            providerId,
          }
        }
        if (!probe?.success) {
          return {
            ok: false,
            stage: "probe",
            error: new Error(probe?.error || "Provider connection test failed"),
            providerId,
          }
        }

        if (operations.activation.mode === "activate") {
          await operations.activation.setSelectedModel({
            provider: providerId,
            model: model.model_id,
            model_id: model.id,
          })
          await operations.activation.refreshSettings()
        }

        return {
          ok: true,
          providerId,
          modelId: model.id,
          modelName: model.model_id,
        }
      } catch (error) {
        return {
          ok: false,
          stage: "model",
          error: asError(error, "Failed to select the connected model"),
          ...(providerId ? { providerId } : {}),
        }
      } finally {
        setIsConnecting(false)
      }
    },
    [operations],
  )

  return { connect, isConnecting }
}
